from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Literal


# === Time Configuration ===
## We need to scale all input times by a factor so that the smallest meaningful unit becomes 1 tick. So let's multiply all input times by TIME_SCALE to convert them into ticks
TICK: int = 1 # One tick = base simulation time unit
TIME_SCALE: int = 1000  # e.g., inputs are in milliseconds → scale by 1000
current_time: int = 0 # Global current time in ticks

@dataclass
class Process:
    pid: int  # Unique ID (0,1,2...)
    arrival_time: int # in ticks (after scaling)
    burst_time: int # in ticks (after scaling)
    remaining_time: int = field(init=False)  # Will be set to burst_time in __post_init__
    wait_time: int = 0  # Accumulated wait time
    turnaround_time: int = 0  # To be calculated
    response_time: int = -1  # First CPU time - arrival time
    start_time: int = -1  # When first started
    completion_time: int = -1  # When finished
    state: Literal["new", "running", "waiting", "ready", "terminated"] 

    def __post_init__(self) -> None:
        if self.arrival_time < 0:
            raise ValueError("arrival_time must be non-negative")
        if self.burst_time <= 0:
            raise ValueError("burst_time must be positive")
        self.remaining_time = self.burst_time
        self.state = "new"
        

class CPUScheduler:
    def select_next_process(self, algorithm: Literal["FCFS", "SJF", "HRRN", "RR", "SRTF"] ) -> None:
        if not self.ready_queue:
            self.current_process = None
            return

        if algorithm == "FCFS":
            self.current_process = self.ready_queue.pop(0)
        elif algorithm == "SJF":
            self.current_process = min(self.ready_queue, key=lambda p: p.remaining_time)
            self.ready_queue.remove(self.current_process)
        elif algorithm == "HRRN":
            # Highest Response Ratio Next: (waiting_time + burst_time) / burst_time
            self.current_process = max(
                self.ready_queue,
                key=lambda p: (self.time - p.arrival_time + p.burst_time) / p.burst_time
            )
            self.ready_queue.remove(self.current_process)
        elif algorithm == "RR":
            self.current_process = self.ready_queue.pop(0)
        elif algorithm == "SRTF":
            self.current_process = min(self.ready_queue, key=lambda p: p.remaining_time)
            self.ready_queue.remove(self.current_process)

    def dispatcher(self) -> None:
        """Handle context switch load phase"""
        if self.in_switch and self.switch_phase == "load":
            if self.switch_remaining > 0:
                self.switch_remaining -= 1
                self.gantt.append((self.time, self.time + 1, -1, "load_context"))
                self.clock_tick(1)
            else:
                self.in_switch = False
                self.switch_phase = None
                if self.current_process and self.current_process.start_time == -1:
                    self.current_process.start_time = self.time
                    self.current_process.response_time = self.time - self.current_process.arrival_time

    def cpu_burst(self, duration: int) -> None:
        """Execute CPU burst for up to 'duration' ticks"""
        if not self.current_process:
            return

        exec_time = min(duration, self.current_process.remaining_time)
        self.current_process.remaining_time -= exec_time

        self.gantt.append((self.time, self.time + exec_time, self.current_process.pid, "execution"))
        self.clock_tick(exec_time)

        if self.current_process.remaining_time <= 0:
            self.current_process.completion_time = self.time
            self.current_process.turnaround_time = self.current_process.completion_time - self.current_process.arrival_time
            self.current_process.wait_time = self.current_process.turnaround_time - self.current_process.burst_time
            # Process finished
            self.current_process = None

    def clock_tick(self, duration: int = 1) -> None:
        global current_time
        self.time += duration
        current_time += duration



# Setup
# Input data
raw_processes_data: List[List[int]] = [
    (6, 1),    # arrival=6 ms, cbt=1 ms
    (10, 7),   # arrival=10 ms, cbt=7 ms
    (2, 9),
    (3, 25),
]
scheduler= CPUScheduler(processes_data=raw_processes_data)


# Example usage

s = CPUScheduler(processes_data, context_switch_time=2)
print(len(s.processes))  # Output: 4
print([f"Process {p.pid}: arrival={p.arrival_time}, burst={p.burst_time}" for p in s.processes])
# Example Input: ['Process 0: arrival=60000, burst=10000', ...]

# To simulate (example with FCFS):
# Sort processes by arrival time first
s.processes.sort(key=lambda p: p.arrival_time)
s.ready_queue = s.processes[:]
s.select_next_process("FCFS")
print(f"Selected: {s.current_process.pid if s.current_process else 'None'}")