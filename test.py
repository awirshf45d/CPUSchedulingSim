from dataclasses import dataclass, field
from typing import Optional, List, Tuple
from .types import (
    SchedulerInput, JobInput, ProcessInput, Process, ReadyQueue, RAM,
    STSAlgorithm, LTSAlgorithm, ContextSwitchPhase, PriorityBand,
    TICK, TIME_SCALE, CURRENT_TIME
)
class CPUScheduler:
    def __init__(
        self,
        input_data: List[Tuple[int, int]],
        context_switch_time: int|False,
        time_quantum: int|False = False,
        # arrival_time_into_job_pool: bool = False
    ) -> None:
        # input_data = [(arrival_time, cpu_burst_time), ...]
        #  if the arrival_time_into_job_pool has set into true, se we the input 
        self.processes_list: List[Process] = []
        for i, (arrival, burst) in enumerate(input_data):
            scaled_arrival = arrival * TIME_SCALE
            scaled_burst = burst * TIME_SCALE
            self.processes_list.append(Process(i, scaled_arrival, scaled_burst))

        self.context_switch_time: int = context_switch_time * TIME_SCALE # scaled context-switch time
        self.half_cs: int = self.context_switch_time // 2 # scaled
        
        self.time_quantum: int|False = time_quantum * TIME_SCALE
        self.time: int = 0 # Don't know what's the purpose of this variable
        
        self.gantt: List[Tuple[int, int, int, str]] = []  # (start, end, pid, event_type). Used by Blender.
        
        self.ready_queues: List[ReadyQueue] = []
        self.job_pool: List[Job] = []

        self.current_process: Optional[Process] = None
        self.current_quantum: int = 0  # For Round-Robin
        self.in_switch: bool = False
        self.switch_phase: ContextSwitchPhase = None  # "cs_update_PCB" or "cs_load_PCB"
        self.switch_remaining: int = 0  # Ticks left in phase        
        self.outgoing_process: Optional[Process] = None  # For save phase
    def __post_init__(self) -> None:
        if self.context_switch_time < 0:
            raise ValueError("context_switch_time must be non-negative")
        if self.time_quantum < 0:
            raise ValueError("time_quantum must be non-negative")
    def long_term_schedular(self, algorithm:LTSAlgorithm) -> None:
        pass
    def short_term_scheduler(self, algorithm: STSAlgorithm ) -> None:
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
    def clock_tick(self) -> None:
        global CURRENT_TIME, TICK
        CURRENT_TIME += TICK