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
    
    # 3. DYNAMIC / INTERNAL FIELDS (init=False)
    remaining_time: int = field(init=False)  # Will be set to burst_time in __post_init__
    state: ProcessState = field(init=False) # Will be set to burst_time in __post_init__
    
    # Statistics
    wait_time: int = 0  # Accumulated wait time, in ticks
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
       
# Scheduler 
## Input type
class SchedulerMode(Enum):
    STANDARD = auto() # Processes, Standard (AT, CBT) 
    MLQ = auto() # Processes, (AT, CBT, Category)

# Input
## Process
InputProcessCategory = Literal["BATCH", "INTERACTIVE", "SYSTEM", "REAL_TIME"]

InputProcessNoCategory = Tuple[float, float] # at, cbt
InputProcessWithCategory = Tuple[float, float, InputProcessCategory] # at, cbt, category (MLQ)

InputList = Union[
    List[InputProcessNoCategory],
    List[InputProcessWithCategory]
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
    mode: SchedulerMode = SchedulerMode.STANDARD  # Default
    if item_len == 3:
        if isinstance(first_item[2], str):
            mode = SchedulerMode.MLQ
        else:
            raise ValueError(f"Unknown input format in 3rd column: {first_item[2]}")
    elif item_len == 2:
        mode = SchedulerMode.STANDARD  # Explicitly set default mode for 2-item case
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

    return mode
    

## Let's scale the time, so smallest meaningful unit of time becomes 1 tick.
InputProcessNoCategoryScaled = Tuple[int, int] # at, cbt
InputProcessWithCategoryScaled = Tuple[int, int, InputProcessCategory] # at, cbt, category (MLQ)
InputListScaled = Union[
    List[InputProcessNoCategoryScaled],
    List[InputProcessWithCategoryScaled]
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
        if scheduler_mode is SchedulerMode.STANDARD:
            scaled_list.append((at_scaled, cbt_scaled))
        elif scheduler_mode is SchedulerMode.MLQ:
            # MLQ Mode: (at, cbt, category) - Category is string, keep as is
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
class ProcessEvents(Enum): # start_time  = end_time
    PROCESS_ARRIVAL = "PROCESS_ARRIVAL"


# --- Logging Data Structure ---
STSAlgo=Literal["FCFS", "SPN", "HRRN", "SRTF", "RR", "MLQ", "MLFQ"]
@dataclass
class SimulationLog:
    algorithm: STSAlgo | None
    start_time: int
    end_time: int
    pid: int | None
    event_type: Union[ProcessEvents, SystemState]


# Ready Queue
@dataclass
class QueueLevel():
    algo: STSAlgo
    queue: List[Process]
    category: ProcessCategory | None = None
    q: int | None = None # only if algorithm is preemptive
    new_event_occurred: bool = False
