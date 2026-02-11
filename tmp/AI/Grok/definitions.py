from enum import Enum, auto
from typing import Literal, Union, List, Optional, Dict, Tuple
from dataclasses import dataclass, field

# === Time Configuration ===
TICK: Literal[1] = 1

class ProcessCategory(Enum):
    BATCH = auto()
    INTERACTIVE = auto()
    SYSTEM = auto()
    REAL_TIME = auto()

class ProcessState(Enum):
    NEW = auto()
    READY = auto()
    RUNNING = auto()
    WAITING = auto()
    TERMINATED = auto()

@dataclass
class Process:
    pid: int
    arrival_time: int
    burst_time: int
    category: Optional[ProcessCategory] = None

    remaining_time: int = field(init=False)
    state: ProcessState = field(init=False)

    wait_time: int = 0
    turnaround_time: int = 0
    start_time: int = -1
    response_time: int = -1
    completion_time: int = -1

    def __post_init__(self):
        self.remaining_time = self.burst_time
        self.state = ProcessState.NEW

@dataclass
class Job:
    jobId: int
    arrival_time: int
    burst_time: int
    memory_needed_kb: float

class SchedulerMode(Enum):
    JOB = auto()
    PROCESS = auto()
    MLQ = auto()

# Input types
InputList = Union[
    List[Tuple[float, float]],
    List[Tuple[float, float, str]],
    List[Tuple[float, float, float]]
]

# Gantt Entry for clean logging
@dataclass
class GanttEntry:
    algorithm: str
    start: float
    end: float
    pid: Optional[int]
    label: str

# Queue Level (for future MLQ/MLFQ)
@dataclass
class QueueLevel:
    algo: str
    q: Optional[int] = None
    queue: List[Process] = field(default_factory=list)
    new_event_occurred: bool = False


# === Validation & Scaling ===
def validate_input_and_determine_scheduler_mode(data_list: InputList, q: float, cs: float) -> SchedulerMode:
    if q <= 0:
        raise ValueError(f"Quantum Time (q) must be positive. Got: {q}")
    if cs < 0:
        raise ValueError(f"Context-Switch Time (cs) must be non-negative. Got: {cs}")
    if not data_list:
        raise ValueError("Input list cannot be empty")

    first = data_list[0]
    length = len(first)

    if length == 2:
        mode = SchedulerMode.PROCESS
    elif length == 3:
        mode = SchedulerMode.MLQ if isinstance(first[2], str) else SchedulerMode.JOB
    else:
        raise ValueError(f"Invalid input format. Item length must be 2 or 3.")

    for i, item in enumerate(data_list):
        at, cbt = item[0], item[1]
        if at < 0 or cbt <= 0:
            raise ValueError(f"Invalid AT/CBT at index {i}")

    return mode


def _get_decimal_places(number: float, max_digits: int = 5) -> int:
    fmt = f"{{:.{max_digits}f}}"
    s = fmt.format(number).rstrip('0')
    return len(s.split('.')[1]) if '.' in s else 0


def scale_input_time(
    data_list: InputList,
    q: float,
    cs: float,
    scheduler_mode: SchedulerMode,
    max_precision: int = 5
) -> Tuple[List, int, int, int]:
    time_values = [q, cs]
    for item in data_list:
        time_values.extend([item[0], item[1]])

    max_decimals = max(_get_decimal_places(val, max_digits=max_precision) for val in time_values)
    TIME_SCALE = 10 ** max_decimals

    q_scaled = int(round(q * TIME_SCALE))
    cs_scaled = int(round(cs * TIME_SCALE))

    scaled_list = []
    for item in data_list:
        at_s = int(round(item[0] * TIME_SCALE))
        bt_s = int(round(item[1] * TIME_SCALE))
        if scheduler_mode is SchedulerMode.PROCESS:
            scaled_list.append((at_s, bt_s))
        elif scheduler_mode is SchedulerMode.MLQ:
            scaled_list.append((at_s, bt_s, item[2]))
        else:  # JOB
            scaled_list.append((at_s, bt_s, item[2]))

    print(f"[DEBUG] Time Scale applied: {TIME_SCALE}x (max decimals: {max_decimals})")
    return scaled_list, q_scaled, cs_scaled, TIME_SCALE