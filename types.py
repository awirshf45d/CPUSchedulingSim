from enum import Enum, auto
from typing import Literal, TypeAlias, Union, List, Dict, Tuple, Set, Any, Union, Optional
from dataclasses import dataclass, field
# Enumeration: It is a way to define a fixed set of named values that belong together. (.name, .value)
# dataclass, field: better syntax, easier to implement types.
## field: "The core problem: mutable defaults are dangerous" and dataclasses.field() gives you more control.
### For immutable default values, you use default= (directly in the annotation or via field(default=...)).


# === Time Configuration ===
## We need to scale all input times by a factor so that the smallest meaningful unit becomes 1 tick. So let's multiply all input times by TIME_SCALE to convert them into ticks
TICK: Literal[1] = 1 # One tick = base simulation time unit
TIME_SCALE: int = 1000  # e.g., inputs are in milliseconds → scale by 1000
CURRENT_TIME: int = 0 # Global current time in ticks


# Scheduling
## algorithms
STSAlgorithm = Literal["FCFS", "SPN", "HRRN", "RR", "SRTF", "MLQ", "MLFQ"]
LTSAlgorithm = Literal["FIFO", "SJF", "Random"]
## Context Switch Phases
ContextSwitchPhase=Literal["save","load"]


# Process
## Process categories (used by MLQ algorithm)
ProcessCategory = Literal["real_time", "system", "interactive", "batch"]
## Process States
ProcessState = Literal["new", "running", "waiting", "ready", "terminated"]

@dataclass
class Process:
    pid: int 
    arrival_time: int # in ticks
    burst_time: int # in ticks
    remaining_time: int = field(init=False)  # Will be set to burst_time in __post_init__
    wait_time: int = 0  # Accumulated wait time, in ticks
    turnaround_time: int = 0  # To be calculated, in ticks
    start_time: int = -1  # When first started(state changed to running for the first time), in ticks
    response_time: int = -1  # start_time (First CPU time) - arrival_time, in ticks
    completion_time: int = -1  # When finished
    state: ProcessState = field(init=False)
    category: ProcessCategory
    memory_needed_kb: float = 0.0  # Added for jobs

    def __post_init__(self) -> None:
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative")
        if self.burst_time <= 0:
            raise ValueError("burst_time must be positive")
        self.remaining_time = self.burst_time
        self.state = "new"


# Ready Queue + RAM
## Priority bands for MLQ,MLFQ
class PriorityBand(Enum):
    REAL_TIME   = (0, 5)    # Highest priority – e.g., RR with small quantum
    SYSTEM      = (6, 11)   # System processes 
    INTERACTIVE = (12, 17)  # User-interactive – RR to ensure responsiveness
    BATCH       = (18, 23)  # Background/batch – Must be Non-Preemptive(FCFS, SPN, HRRN)
    UNIFIED     = (0, 23)   # For Single-queue mode (No MLQ, MLFQ algorithms)

@dataclass
class ReadyQueue:
    id: int
    algorithm: STSAlgorithm
    priority_band: PriorityBand
    quantum_time: Optional[int] # in ticks
    type: ProcessCategory
    ready_queue: List[Process] = field(default_factory=list, init=False)
    # Helper properties
    @property
    def base_priority(self) -> int:
        return self.priority_band.value[0]
    
    @property
    def high_priority(self) -> int:
        return self.priority_band.value[1]
    
    @property
    def is_empty(self) -> bool:
        return len(self.ready_queue) == 0   

## RAM
@dataclass
class RAM:
    size_in_kb: Optional[float]
    free_size: Optional[float] = field(init=False)
    ready_queues: List[ReadyQueue] = field(default_factory=list, init=False)
    
    def __post_init__(self) -> None:
        if (self.size_in_kb is not None) and self.size_in_kb <= 0:
            raise ValueError("The size of memory must be a positive float")
        self.free_size = self.size_in_kb if self.size_in_kb is not None else float('inf')  # Infinite if None
    def add_queue(self, queue: ReadyQueue) -> None:
        self.ready_queues.append(queue) # Do we need update the free_size?
        

# === Input specification for processes ===
@dataclass(frozen=True)
class JobInput:
    """Input for a job (enters job pool, needs memory admission)"""
    arrival_time: float # ms, Arrival to job pool
    burst_time: float # ms, CPU burst        
    memory_needed_kb: float        # Required RAM for this job
    category: ProcessCategory = "general"  # For MLFQ queue assignment after admission
    # Scaled values – computed once when object is created
    arrival_time_ticks: int = field(init=False)
    burst_time_ticks: int = field(init=False)

    def __post_init__(self):
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative")
        if self.burst_time <= 0:
            raise ValueError("burst_time must be positive")
        if self.memory_needed_kb <= 0:
            raise ValueError("memory_needed_kb must be positive")
        object.__setattr__(self, 'arrival_time_ticks', self.arrival_time * TIME_SCALE)
        object.__setattr__(self, 'burst_time_ticks', self.burst_time * TIME_SCALE)

@dataclass(frozen=True)
class ProcessInput:
    """Input for a process (direct to ready queue, assumed in memory)"""
    arrival_time: float              # ms, Arrival to ready queue
    burst_time: float               # ms, CPU burst
    quantum_time: float             # quantum_time
    category: ProcessCategory = "general"  # For MLFQ queue assignment
    # Scaled values – computed once when object is created
    arrival_time_ticks: int = field(init=False)
    burst_time_ticks: int = field(init=False)

    def __post_init__(self):
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative")
        if self.burst_time <= 0:
            raise ValueError("burst_time must be positive")
        object.__setattr__(self, 'arrival_time_ticks', self.arrival_time * TIME_SCALE)
        object.__setattr__(self, 'burst_time_ticks', self.burst_time * TIME_SCALE)

## Conifg

@dataclass(frozen=True)
class ReadyQueueConfig:
    quantum_time: Optional[float] = None  # ms, scaled later
    type: ProcessCategory
    priority_band: PriorityBand = field(init=False)
    algorithm: STSAlgorithm

    def __post_init__(self):
        category2priority_band = {
            "real_time": PriorityBand.REAL_TIME,
            "system": PriorityBand.SYSTEM,
            "interactive": PriorityBand.INTERACTIVE,
            "batch": PriorityBand.BATCH,
            "general": PriorityBand.UNIFIED
        }
        object.__setattr__(self, 'priority_band', category2priority_band.get(self.type))
                
        if (self.algorithm == "RR" or self.algorithm == "SRTF") and self.quantum_time is None:
            raise ValueError("quantum_time required for Preemptive algorithms: RR, SRTF")
        if self.type == "batch" and (self.algorithm == "RR" or self.algorithm == "SRTF"):
            raise ValueError("MLQ: \"batch\" ready queue required a Non-Preemptive algorithm: [\"FCFS\", \"SPN\", \"HRRN\"]")

@dataclass(frozen=True)
class SchedulerConfig:
    kind: Literal["job", "process"]
    ready_queues: List[ReadyQueueConfig]
    inputs: List[Union[JobInput, ProcessInput]]
    main_memory_size_kb: Optional[float] = None

    def __post_init__(self):
        # Validate ready_queues logic
        if len(self.ready_queues) == 1:
            rq = self.ready_queues[0]
            if rq.type != "general" or rq.priority_band != PriorityBand.UNIFIED or (rq.algorithm):
                raise ValueError(f"Single queue must have type 'general' and priority_band {PriorityBand.UNIFIED}")
            # Assuming MLQ/MLFQ not in STSAlgorithm, no need to check algorithm
        elif len(self.ready_queues) > 1:
            types = [rq.type for rq in self.ready_queues]
            if len(set(types)) != len(types):
                raise ValueError("Duplicate types in ready_queues")
            if "general" in types:
                raise ValueError("'general' type not allowed in multi-queue setup")
            bands = [rq.priority_band for rq in self.ready_queues]
            if len(set(bands)) != len(bands):
                raise ValueError("Duplicate priority_bands in ready_queues")
        else:
            raise ValueError("At least one ready_queue required")

        # Validate inputs based on kind
        if self.kind == "job":
            if not all(isinstance(inp, JobInput) for inp in self.inputs):
                raise ValueError("All inputs must be JobInput for kind='job'")
            if self.main_memory_size_kb is None:
                raise ValueError("main_memory_size_kb required for kind='job'")
        elif self.kind == "process":
            if not all(isinstance(inp, ProcessInput) for inp in self.inputs):
                raise ValueError("All inputs must be ProcessInput for kind='process'")
            if self.main_memory_size_kb is not None:
                raise ValueError("main_memory_size_kb should not be provided for kind='process'")

        # Validate input categories match ready_queues types
        available_types = {rq.type for rq in self.ready_queues}
        for inp in self.inputs:
            if inp.category not in available_types:
                raise ValueError(f"Input category '{inp.category}' does not match any ready_queue type")
