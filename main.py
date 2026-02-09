from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from .types import (
    SchedulerInput, JobInput, ProcessInput, Process, ReadyQueue, RAM,
    STSAlgorithm, LTSAlgorithm, ContextSwitchPhase, PriorityBand,
    TICK, TIME_SCALE, CURRENT_TIME
)

# @dataclass
# class CPUScheduler:
#     inputs: SchedulerInput
#     main_memory_size_kb: Optional[float] = None  # Required if inputs are jobs
#     context_switch_time: float  # Global context switch time in ms
#     default_time_quantum: Optional[float] = None  # Default quantum if not per-queue
#     default_sts_algorithm: STSAlgorithm = "FCFS"  # Default if no MLFQ config
#     default_lts_algorithm: LTSAlgorithm = "FIFO"  # For long-term admission

#     # Internal state
#     processes: List[Process] = field(default_factory=list, init=False)
#     job_pool: List[JobInput] = field(default_factory=list, init=False)
#     ram: RAM = field(init=False)
#     ready_queues: List[ReadyQueue] = field(default_factory=list, init=False)
#     current_process: Optional[Process] = field(default=None, init=False)
#     gantt: List[Tuple[int, int, int, str]] = field(default_factory=list, init=False)  # (start, end, pid, event)
#     time: int = field(default=0, init=False)
#     in_switch: bool = field(default=False, init=False)
#     switch_phase: Optional[ContextSwitchPhase] = field(default=None, init=False)
#     switch_remaining: int = field(default=0, init=False)
#     outgoing_process: Optional[Process] = field(default=None, init=False)
#     current_quantum: int = field(default=0, init=False)  # For RR tracking
#     context_switch_time_ticks: int = field(init=False)
#     all_terminated: bool = field(default=False, init=False)

#     def __post_init__(self) -> None:
#         # Scale context switch time
#         self.context_switch_time_ticks = int(self.context_switch_time * TIME_SCALE)
#         half_cs = self.context_switch_time_ticks // 2

#         # Initialize RAM
#         if self.main_memory_size_kb is not None:
#             self.ram = RAM(self.main_memory_size_kb)
#         else:
#             self.ram = RAM(None)  # No memory limit for processes

#         # Process inputs and create Processes
#         used_categories = set()
#         is_jobs = isinstance(self.inputs, list) and self.inputs and isinstance(self.inputs[0], JobInput)
#         if is_jobs:
#             if self.main_memory_size_kb is None:
#                 raise ValueError("main_memory_size_kb required for JobInput")
#             for i, inp in enumerate(self.inputs):
#                 proc = Process(
#                     pid=i,
#                     arrival_time=inp.arrival_time_ticks,
#                     burst_time=inp.burst_time_ticks,
#                     category=inp.category
#                 )
#                 proc.memory_needed_kb = inp.memory_needed_kb  # Assuming added to Process
#                 self.job_pool.append(proc)
#                 used_categories.add(inp.category)
#         else:
#             for i, inp in enumerate(self.inputs):
#                 proc = Process(
#                     pid=i,
#                     arrival_time=inp.arrival_time_ticks,
#                     burst_time=inp.burst_time_ticks,
#                     category=inp.category
#                 )
#                 proc.memory_needed_kb = 0.0  # No memory check
#                 self.processes.append(proc)
#                 used_categories.add(inp.category)

#         # Create ready queues dynamically based on used categories
#         queue_id = 0
#         for cat in used_categories:
#             band = self._get_priority_band_for_category(cat)
#             algorithm, time_quantum_ms = self._get_algorithm_and_quantum_for_band(band)
#             queue = ReadyQueue(
#                 id=queue_id,
#                 algorithm=algorithm,
#                 priority_band=band,
#                 time_quantum=int(time_quantum_ms * TIME_SCALE) if time_quantum_ms else None
#             )
#             self.ready_queues.append(queue)
#             self.ram.add_queue(queue)
#             queue_id += 1

#         # Sort queues by priority (lowest number = highest priority)
#         self.ready_queues.sort(key=lambda q: q.priority_band.value[0])

#         # If no MLFQ (only general), use unified queue
#         if not self.ready_queues:
#             unified_queue = ReadyQueue(
#                 id=0,
#                 algorithm=self.default_sts_algorithm,
#                 priority_band=PriorityBand.UNIFIED,
#                 time_quantum=int(self.default_time_quantum * TIME_SCALE) if self.default_time_quantum else None
#             )
#             self.ready_queues.append(unified_queue)
#             self.ram.add_queue(unified_queue)

#     def _get_priority_band_for_category(self, cat: str) -> PriorityBand:
#         mapping = {
#             "real_time": PriorityBand.REAL_TIME,
#             "system": PriorityBand.SYSTEM,
#             "interactive": PriorityBand.INTERACTIVE,
#             "batch": PriorityBand.BATCH,
#             "general": PriorityBand.UNIFIED,
#         }
#         return mapping.get(cat, PriorityBand.UNIFIED)

#     def _get_algorithm_and_quantum_for_band(self, band: PriorityBand) -> Tuple[STSAlgorithm, Optional[float]]:
#         # Default per-band configs (customize as needed)
#         if band == PriorityBand.REAL_TIME:
#             return "RR", 2.0
#         elif band == PriorityBand.SYSTEM:
#             return "SJF", None
#         elif band == PriorityBand.INTERACTIVE:
#             return "RR", 4.0
#         elif band == PriorityBand.BATCH:
#             return "FCFS", None
#         else:  # UNIFIED or general
#             return self.default_sts_algorithm, self.default_time_quantum

#     def run(self) -> None:
#         """Run the simulation until all processes are terminated."""
#         global CURRENT_TIME
#         self.time = 0
#         CURRENT_TIME = 0

#         while not self.all_terminated:
#             # Handle arrivals at current time
#             self._handle_arrivals()

#             # Long-term scheduler if job_pool not empty
#             if self.job_pool:
#                 self.long_term_scheduler(self.default_lts_algorithm)

#             # If in context switch, continue it
#             if self.in_switch:
#                 self.dispatcher()
#                 self.time += TICK
#                 CURRENT_TIME += TICK
#                 continue

#             # Short-term scheduler if no current process
#             if not self.current_process:
#                 self.short_term_scheduler()

#             # Execute CPU burst (or quantum for RR)
#             if self.current_process:
#                 if self.current_process.remaining_time > 0:
#                     # For RR, check quantum
#                     if self.current_quantum >= self.current_process.queue.time_quantum:  # Assuming process has .queue ref
#                         self._preempt_and_switch()
#                     else:
#                         self.cpu_burst(TICK)
#                         self.current_quantum += TICK
#                 else:
#                     self._terminate_process()

#             # Check if all done
#             self.all_terminated = all(p.state == "terminated" for p in self.processes + self.job_pool)

#             self.time += TICK
#             CURRENT_TIME += TICK

#     def _handle_arrivals(self) -> None:
#         """Move arrived processes from processes list to ready queues (for ProcessInput)."""
#         arrived = [p for p in self.processes if p.arrival_time <= self.time and p.state == "new"]
#         for p in arrived:
#             queue = self._find_queue_for_process(p)
#             queue.ready_queue.append(p)
#             p.state = "ready"
#             self.processes.remove(p)  # Move to queue

#     def long_term_scheduler(self, algorithm: LTSAlgorithm) -> None:
#         """Admit jobs from job_pool to ready queues if memory available."""
#         # Simple FIFO for now
#         if algorithm == "FIFO":
#             candidates = sorted(self.job_pool, key=lambda p: p.arrival_time)
#         # ... other algorithms like SJF by burst_time

#         for proc in candidates[:]:  # Copy to avoid modification issues
#             if proc.arrival_time > self.time:
#                 continue
#             if self.ram.free_size >= proc.memory_needed_kb:
#                 queue = self._find_queue_for_process(proc)
#                 queue.ready_queue.append(proc)
#                 proc.state = "ready"
#                 self.ram.free_size -= proc.memory_needed_kb
#                 self.job_pool.remove(proc)

#     def short_term_scheduler(self) -> None:
#         """Select next process from highest priority non-empty queue."""
#         for queue in self.ready_queues:
#             if not queue.is_empty:
#                 # Apply queue's algorithm to select from its ready_queue
#                 if queue.algorithm == "FCFS":
#                     self.current_process = queue.ready_queue.pop(0)
#                 elif queue.algorithm == "SJF":
#                     self.current_process = min(queue.ready_queue, key=lambda p: p.remaining_time)
#                     queue.ready_queue.remove(self.current_process)
#                 # ... implement others like HRRN, RR, SRTF
#                 self.current_process.queue = queue  # Temp ref for quantum check
#                 self.current_quantum = 0
#                 # Start context switch if needed
#                 if self.context_switch_time_ticks > 0:
#                     self._initiate_context_switch()
#                 return

#     def _initiate_context_switch(self) -> None:
#         self.in_switch = True
#         self.switch_phase = "save"
#         self.switch_remaining = self.context_switch_time_ticks // 2
#         self.outgoing_process = self.current_process  # For save, but if new, no outgoing

#     def dispatcher(self) -> None:
#         """Handle context switch phases."""
#         if self.switch_remaining > 0:
#             self.switch_remaining -= TICK
#             event = "save_context" if self.switch_phase == "save" else "load_context"
#             self.gantt.append((self.time, self.time + TICK, -1, event))
#         else:
#             if self.switch_phase == "save":
#                 # Switch to load phase
#                 self.switch_phase = "load"
#                 self.switch_remaining = self.context_switch_time_ticks // 2
#             else:
#                 self.in_switch = False
#                 self.switch_phase = None
#                 if self.current_process.start_time == -1:
#                     self.current_process.start_time = self.time
#                     self.current_process.response_time = self.time - self.current_process.arrival_time

#     def cpu_burst(self, duration: int) -> None:
#         """Execute CPU burst for given duration."""
#         if not self.current_process:
#             return
#         exec_time = min(duration, self.current_process.remaining_time)
#         self.current_process.remaining_time -= exec_time
#         self.gantt.append((self.time, self.time + exec_time, self.current_process.pid, "execution"))
#         self.time += exec_time  # But since tick-by-tick, duration=TICK

#     def _preempt_and_switch(self) -> None:
#         """Preempt current process for RR/SRTF, put back to queue."""
#         if self.current_process.remaining_time > 0:
#             self.current_process.queue.ready_queue.append(self.current_process)
#         self.current_process = None
#         self._initiate_context_switch()

#     def _terminate_process(self) -> None:
#         """Terminate completed process."""
#         self.current_process.completion_time = self.time
#         self.current_process.turnaround_time = self.completion_time - self.current_process.arrival_time
#         self.current_process.wait_time = self.turnaround_time - self.current_process.burst_time
#         self.current_process.state = "terminated"
#         # Free memory if any
#         self.ram.free_size += self.current_process.memory_needed_kb
#         self.current_process = None
#         self._initiate_context_switch()  # Switch after termination

#     def _find_queue_for_process(self, proc: Process) -> ReadyQueue:
#         """Find matching queue based on category."""
#         target_band = self._get_priority_band_for_category(proc.category)
#         for q in self.ready_queues:
#             if q.priority_band == target_band:
#                 return q
#         raise ValueError(f"No queue for category {proc.category}")

# # Setup
# # Input data

# ## Processes (no memory check)
# process_inputs: List[ProcessInput] = [
#     # Defaults: category="general"
#     # Processes -> Arrival time to the Ready queue(s)[ready] -> STS -> CPU[running]
#     ProcessInput(arrival_time_ms=6, cbt=1),
#     ProcessInput(arrival_time_ms=10, cbt=7),
# ]

# # Pass to scheduler (detect type via isinstance)
# scheduler = CPUScheduler(
#     inputs=process_inputs, 
#     main_memory_size_kb=1024.0 | None,
# )
# scheduler= CPUScheduler(input_data=process_inputs, context_switch_time=2, time_quantum=5)


from enum import Enum

TICK = int(0)
current_time = int(0)


class SystemState(Enum):
    IDLE = "IDLE"
    CS_SAVE = "CS_SAVE"
    CS_LOAD = "CS_LOAD"
    EXECUTING = "EXECUTING"

class Process:    # Defines the Process Object
    def __init__(self, pid, arrival_time, burst_time):
        self.pid = pid  # Unique ID (0,1,2...)
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.remaining_time = burst_time

        # Metrics
        self.wait_time = 0  # Accumulated wait
        self.turnaround_time = 0  # To be calculated
        self.response_time = -1  # First CPU time - arrival
        self.start_time = -1  # When first started
        self.completion_time = -1  # When finished



class CPUScheduler:
    def __init__(self, processes_data, context_switch_time=0, time_quantum=5):
        # processes_data = [[arrival, burst], ...]

        self.processes = []  # processes = [Process(pid, at, bt), Process(pid, at, bt), Process(pid, at, bt), ... ]

        for i, (at, bt) in enumerate(processes_data):
            self.processes.append(Process(i, at, bt))


        self.context_switch_time = context_switch_time
        self.half_cs = context_switch_time // 2    # Save/load duration; assume equal split

        self.time_quantum = time_quantum
        self.time = 0

        self.gantt = []  # List of (start, end, pid, event_type) e.g., "arrival", "execution", "save_context", "load_context", "idle"

        self.ready_queue = []

        self.current_process = None
        self.current_quantum = 0  # For RR
        self.in_switch = False
        self.switch_phase = None  # "save" or "load"
        self.switch_remaining = 0  # Ticks left in phase        
        self.outgoing_process = None  # For save phase


    def select_next_process(self, algorithm):
        
        if self.ready_queue:

            if algorithm == "FCFS":
                # self.current_process = ...
                pass
            elif algorithm == "SJF":
                # self.current_process = ...
                pass
            elif algorithm == "HRRN":
                # self.current_process = ...
                pass
            elif algorithm == "Round-Robin":
                # self.current_process = ...
                pass
            elif algorithm == "SRTF":
                # self.current_process = ...
                pass
            else:
                raise ValueError(f"Unknown Scheduler algorithm: {algorithm}")

        else:
            self.current_process = None


    def dispatcher():
        # doing context switch (load)
        pass


    def cpu_burst():
        pass

    def clock_tick(duration):
        global current_time

        for i in range(duration):
            current_time += TICK
        
        
        
# processes_data = [[at0, bt0], [at1, bt1], [at2, bt2], [at3, bt3]]
# processes_data = [[1, 6], [8, 5], [10.25, 2], [17.50, 3]]

processes_data = [ [10000, 60000], [80000, 50000], [102500, 20000], [175000, 30000] ]

s = CPUScheduler(processes_data, context_switch_time=2)
print(len(s.processes))
print(s.processes)

