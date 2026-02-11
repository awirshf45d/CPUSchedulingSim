from enum import Enum, auto
from typing import Literal, Union, List, Dict, Tuple, Set, Any, Union, Optional
from dataclasses import dataclass, field
# Enumeration: It is a way to define a fixed set of named values that belong together. (.name, .value)
# dataclass, field: better syntax, easier to implement types.
## field: "The core problem: mutable defaults are dangerous" and dataclasses.field() gives you more control.
### For immutable default values, you use default= (directly in the annotation or via field(default=...)).


# === Time Configuration ===
## We need to scale all input times by a factor so that the smallest meaningful unit becomes 1 tick. So let's multiply all input times by TIME_SCALE to convert them into ticks
TICK: Literal[1] = 1 # One tick = base simulation time unit
TIME_SCALE: int = 1


# Process
## Process Categories
class ProcessCategory(Enum):
    # All the categories are only used by MLQ.
    BATCH = auto() # base priority: 0, automatically gets 1
    INTERACTIVE = auto() # base priority: 32, 2
    SYSTEM = auto() # base priority: 64, 3
    REAL_TIME = auto() # base priority: 96, 4

## Process States
class ProcessState(Enum):
    NEW = auto()
    READY = auto()
    RUNNING = auto()
    WAITING = auto()
    TERMINATED = auto()
@dataclass
class Process:
    # MANDATORY FIELDS (No defaults)
    pid: int
    arrival_time: int       # in ticks
    burst_time: int         # in ticks
    _process_ready_queue_id: int = field(init=False)

    category: ProcessCategory | None = None # If the category isn't None, then we only wanna see the output for MLQ
    priority: float = 0     # Higher value = Higher priority
    
    # 3. DYNAMIC / INTERNAL FIELDS (init=False)
    remaining_time: int = field(init=False)  # Will be set to burst_time in __post_init__
    state: ProcessState = field(init=False) # Will be set to burst_time in __post_init__
    
    # Statistics
    wait_time: int = -1  # Accumulated wait time, in ticks
    turnaround_time: int = -1  # To be calculated, in ticks
    start_time: int = -1  # When first started(state changed to running for the first time), in ticks
    response_time: int = -1  # start_time (First CPU time) - arrival_time, in ticks
    completion_time: int = -1  # When finished

    def __post_init__(self) -> None:
        self.remaining_time = self.burst_time
        self.state = ProcessState.NEW
    
    @property
    def process_ready_queue_id(self) -> int:
        return self._process_ready_queue_id
    
    @process_ready_queue_id.setter
    def process_ready_queue_id(self, value: int) -> None:
        if value < 0:
            raise ValueError("process_ready_queue_id cannot be negative")
        self._process_ready_queue_id = value
# Job
## Amir: This section it's not complete yet. so yeah, it doesn't make sense yet. 
@dataclass
class Job:
    jobId: int
    arrival_time: int # in ticks, Arrival to job pool
    burst_time: int # in ticks, CPU burst        
    memory_needed_kb: float        # Required RAM for this job
       
# Scheduler 
## Input type
class SchedulerMode(Enum):
    JOB = auto() # Jobs, (AT, CBT, Memory)
    PROCESS = auto() # Processes, Standard (AT, CBT) 
    MLQ = auto() # Processes, (AT, CBT, Category)

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
    time_values = [q, cs/2] # so half_cs is an int!
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

# --- Logging Data Structure ---
STSAlgo=Literal["FCFS", "SPN", "HRRN", "SRTF", "RR", "MLQ", "MLFQ"]
LTSAlgo=Literal["FIFO","SJF", "Random"]
@dataclass
class SimulationLog:
    algorithm: Union[STSAlgo,LTSAlgo] | None
    start_time: float
    end_time: float
    id: int | None # Job ID or Process ID
    event_type: Union[EventType,SystemState]


# Ready Queue, JobPool
@dataclass
class QueueLevel():
    algo: STSAlgo
    queue: List[Process]
    category: ProcessCategory | None = None
    q: int | None = None # only if algorithm is preemptive
    new_event_occurred: bool = False
@dataclass
class JobPool():
    algo: LTSAlgo
    pool: List[Job]
    new_event_occurred: bool = False