from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple, Any, Union, Literal

# --- Constants ---
TIME_SCALE = 10000  # Scale 1s to 10,000 ticks to handle floats like 0.0001
# Used for display formatting
PID_PREFIX = "P"

# --- Enums ---
class SystemState(Enum):
    IDLE = auto()
    EXECUTING = auto()
    CS_SAVE = auto()
    CS_LOAD = auto()

class Algorithm(Enum):
    FCFS = "FCFS"
    RR = "RR"
    SPN = "SPN"   # Shortest Process Next
    SRTF = "SRTF" # Shortest Remaining Time First
    HRRN = "HRRN" # Highest Response Ratio Next

# --- Data Structures ---

@dataclass
class Process:
    pid: int
    arrival_time_ticks: int
    burst_time_ticks: int
    priority: int = 0  # Lower number = Higher priority
    
    # Dynamic State
    remaining_time_ticks: int = 0
    wait_time_ticks: int = 0
    start_time_ticks: Optional[int] = None
    completion_time_ticks: Optional[int] = None
    
    def __post_init__(self):
        self.remaining_time_ticks = self.burst_time_ticks

    @property
    def turnaround_time_ticks(self) -> int:
        if self.completion_time_ticks is None:
            return 0
        return self.completion_time_ticks - self.arrival_time_ticks

    @property
    def response_ratio(self) -> float:
        # For HRRN: (Wait + Burst) / Burst
        if self.burst_time_ticks == 0: return 0
        return (self.wait_time_ticks + self.burst_time_ticks) / self.burst_time_ticks

@dataclass
class ReadyQueue:
    priority_band: int
    algorithm: Algorithm
    quantum_ticks: int = 0  # Only for RR
    processes: List[Process] = field(default_factory=list)

    def add_process(self, process: Process):
        """Adds process. Sorting happens at retrieval time or insertion depending on logic."""
        self.processes.append(process)
        # Note: We sort dynamically when peeking because variable metrics (like Wait Time for HRRN) change every tick.

    def peek_next(self) -> Optional[Process]:
        if not self.processes:
            return None
        
        # Sort logic based on Algorithm
        if self.algorithm == Algorithm.FCFS:
            return self.processes[0] # Head of line
            
        elif self.algorithm == Algorithm.RR:
            return self.processes[0] # FIFO for Round Robin
            
        elif self.algorithm == Algorithm.SPN:
            # Shortest Process Next (Non-preemptive usually, but we sort by burst)
            return min(self.processes, key=lambda p: p.burst_time_ticks)
            
        elif self.algorithm == Algorithm.SRTF:
            # Shortest Remaining Time First
            return min(self.processes, key=lambda p: p.remaining_time_ticks)
            
        elif self.algorithm == Algorithm.HRRN:
            # Highest Response Ratio Next
            return max(self.processes, key=lambda p: p.response_ratio)
            
        return self.processes[0]

    def pop_next(self) -> Optional[Process]:
        p = self.peek_next()
        if p:
            self.processes.remove(p)
        return p

@dataclass
class GanttSegment:
    start_tick: int
    end_tick: int
    label: str
    pid: Optional[int] = None

# Input
## Process
InputProcessCategory = Literal["BATCH", "INTERACTIVE", "SYSTEM", "REAL_TIME"]

InputProcessNoCategory = Tuple[float, float] # at, cbt
InputProcessWithCategory = Tuple[float, float, InputProcessCategory] # at, cbt, category (MLQ)
InputJob = Tuple[float, float, float] # at (arrival time to job pool), cbt, memory_needed_in_kb

InputList = Union[
    List[InputProcessNoCategory],
    List[InputProcessWithCategory],
    List[InputJob]
]

def validate_input_and_determine_scheduler_mode(
    data_list: InputList,
    q: float,
    cs: float) -> SchedulerMode:
    # 1. q, cs
    if q <= 0:
        raise ValueError(f"Quantum Time (q) must be positive. Got: {q}")
    if cs < 0:
        raise ValueError(f"Context-Switch Time (cs) must be non-negative. Got: {cs}")
    # 2. List Validation
    # We inspect the structure of the first element
    if not data_list:
        raise ValueError("Input list cannot be empty")

    first_item = data_list[0]
    item_len = len(first_item)

    mode: SchedulerMode = SchedulerMode.PROCESS # Default
    if item_len == 2:
        mode = SchedulerMode.PROCESS
    elif item_len == 3:
        # Check 3rd element type to distinguish MLQ vs JOB
        third_val = first_item[2]
        if isinstance(third_val, str):
            mode = SchedulerMode.MLQ
        elif isinstance(third_val, (int, float)):
            mode = SchedulerMode.JOB
        else:
            raise ValueError(f"Unknown input format in 3rd column: {third_val}")
    else:
        raise ValueError(f"Invalid input format. Item length must be 2 or 3. Got: {item_len}")

    # 4. Validate All Elements in List
    for i, item in enumerate(data_list):
        at = item[0]
        cbt = item[1]

        if at < 0:
            raise ValueError(f"Item at index {i}: Arrival Time must be non-negative. Got: {at}")
        if cbt <= 0:
            raise ValueError(f"Item at index {i}: CPU Burst Time must be positive. Got: {cbt}")

        # Specific Validations
        if mode is SchedulerMode.JOB:
            memory = item[2]
            if memory <= 0:
                raise ValueError(f"Item at index {i}: Memory size must be positive. Got: {memory}")
                
    return mode
    

## Let's scale the time, so smallest meaningful unit of time becomes 1 tick.
InputProcessNoCategoryScaled = Tuple[int, int] # at, cbt
InputProcessWithCategoryScaled = Tuple[int, int, InputProcessCategory] # at, cbt, category (MLQ)
InputJobScaled = Tuple[int, int, float] # at (arrival time to job pool), cbt, memory_needed_in_kb
InputListScaled = Union[
    List[InputProcessNoCategoryScaled],
    List[InputProcessWithCategoryScaled],
    List[InputJobScaled]
]

# --- Helper to calculate decimals ---

def _get_decimal_places(number: float, max_digits: int = 5) -> int:
    """
    Counts meaningful decimal places. 
    max_digits: The maximum precision to check (standard float precision is ~15-17).
    """
    # dynamically create the format string, e.g., "{:.15f}"
    fmt = f"{{:.{max_digits}f}}" 
    
    # format the number and strip trailing zeros
    s = fmt.format(number).rstrip('0')
    
    if '.' in s:
        return len(s.split('.')[1])
    return 0

def scale_input_time(
    data_list: InputList, 
    q: float, 
    cs: float,
    scheduler_mode: SchedulerMode,
    max_precision: int = 5
) -> Tuple[InputListScaled, int, int]: # Returns (scaled_list, scaled_q, scaled_cs)
    
    # 1. Collect all Time-Related values to find max precision
    # We look at Q, CS, Arrival Times, and CPU Burst Times.
    # Note: We do NOT look at Memory size (for Jobs) as that is not a time unit.
    time_values = [q, cs]
    for item in data_list:
        time_values.append(item[0]) # at
        time_values.append(item[1]) # cbt

    # 2. Determine Max Decimal Places
    max_decimals = 0
    for val in time_values:
        d = _get_decimal_places(val, max_digits=max_precision)
        if d > max_decimals:
            max_decimals = d
            
    # 3. Calculate Scale Factor
    # If max_decimals is 0 (all integers), scale is 1
    # If max_decimals is 2 (e.g. 10.25), scale is 100
    TIME_SCALE = 10 ** max_decimals

    # 4. Scale Q and CS
    # using round() to handle float imprecision (e.g., 3.000000004 -> 3)
    q_scaled = int(round(q * TIME_SCALE))
    cs_scaled = int(round(cs * TIME_SCALE))

    # 5. Scale the List
    scaled_list: InputListScaled = []
    
    for item in data_list:
        # Scale AT and CBT
        at_scaled = int(round(item[0] * TIME_SCALE))
        cbt_scaled = int(round(item[1] * TIME_SCALE))
        
        # Reconstruct the tuple/list based on Scheduler mode
        if scheduler_mode is SchedulerMode.PROCESS:
            scaled_list.append((at_scaled, cbt_scaled))
        elif scheduler_mode is SchedulerMode.MLQ:
            # MLQ Mode: (at, cbt, category) - Category is string, keep as is
            scaled_list.append((at_scaled, cbt_scaled, item[2]))
        elif scheduler_mode is SchedulerMode.JOB:
            # JOB Mode: (at, cbt, memory) - Memory is size, DO NOT SCALE
            scaled_list.append((at_scaled, cbt_scaled, item[2]))
    print(f"[DEBUG] Automatic Time Scale: {TIME_SCALE} (Max decimals: {max_decimals})")
    print(f"[DEBUG] Scaled List: {scaled_list}")
    
    return scaled_list, q_scaled, cs_scaled


# Logs:
## Specific System States
class SystemState(Enum):
    IDLE       = "IDLE"
    CS_SAVE    = "CS_SAVE"     # context save
    CS_LOAD    = "CS_LOAD"     # context load
    EXECUTING  = "EXECUTING"

class EventType(Enum):
    # State transitions / important moments
    PROCESS_ARRIVAL    = "PROCESS_ARRIVAL"    # First Process arrival: System is no longer IDLE
    JOB_ARRIVAL        = "JOB_ARRIVAL"
    CS_SAVE_START      = "CS_SAVE_START"      # entering CS_SAVE
    CS_SAVE_COMPLETE   = "CS_SAVE_COMPLETE"   # leaving CS_SAVE
    CS_LOAD_START      = "CS_LOAD_START"      # entering CS_LOAD
    CS_LOAD_ABORT      = "CS_LOAD_ABORT"      # interrupt occurs
    CS_LOAD_COMPLETE   = "CS_LOAD_COMPLETE"   # leaving CS_LOAD
    PROCESS_DISPATCH   = "PROCESS_DISPATCH"   # → EXECUTING
    PROCESS_PREEMPT    = "PROCESS_PREEMPT"    # → not EXECUTING
    PROCESS_COMPLETION = "PROCESS_COMPLETION" # → IDLE or next process
    TIMER_INTERRUPT    = "TIMER_INTERRUPT"    # quantum time expired

# # --- Logging Data Structure ---
# STSAlgo=Literal["FCFS", "SPN", "HRRN", "SRTF", "RR", "MLQ", "MLFQ"]
# LTSAlgo=Literal["FIFO","SJF", "Random"]
# @dataclass
# class SimulationLog:
#     algorithm: Union[STSAlgo,LTSAlgo] | None
#     time: float
#     id: int | None # Job ID or Process ID
#     event_type: EventType


# # Ready Queue, JobPool
# @dataclass
# class QueueLevel():
#     category: ProcessCategory | None = None
#     q: int | None = None ## only if algorithm is preemptive
#     algo: STSAlgo
#     queue: List[Process]
#     new_event_occurred: bool = False
# @dataclass
# class JobPool():
#     algo: LTSAlgo
#     pool: List[Job]
#     new_event_occurred: bool = False