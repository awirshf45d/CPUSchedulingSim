from dataclasses import dataclass
from typing import List

# === Time Configuration ===
TICK: int = 1                    # One tick = base simulation time unit
TIME_SCALE: int = 10000           # e.g., inputs are in milliseconds → scale by 1000

current_time: int = 0

@dataclass
class Process:
    pid: int
    arrival_time: int        # in ticks (after scaling)
    burst_time: int          # in ticks (after scaling)
    remaining_time: int = 0

    def __post_init__(self) -> None:
        self.remaining_time = self.burst_time

# === Raw input data (e.g., arrival and burst in milliseconds) ===
raw_processes: List[List[int]] = [
    [6, 1],    # arrival=6 ms, burst=1 ms
    [10, 7],   # arrival=10 ms, burst=7 ms
    [2, 9],
    [3, 25],
]

# === Scale inputs to ticks ===
processes = [
    Process(pid=i,
            arrival_time=at * TIME_SCALE,
            burst_time=bt * TIME_SCALE)
    for i, (at, bt) in enumerate(raw_processes)
]

# Now all times are in ticks!
print("Scaled Processes:")
for p in processes:
    print(f"P{p.pid}: arrival={p.arrival_time} ticks ({p.arrival_time // TIME_SCALE} ms), "
          f"burst={p.burst_time} ticks ({p.burst_time // TIME_SCALE} ms)")