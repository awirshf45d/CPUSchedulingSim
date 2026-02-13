from typing import Literal, Union, List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from definitions import (
    TICK, TIME_SCALE,
    SimulationLog, SystemState, SchedulerMode, EventType,
    Process, Job, ProcessState, ProcessCategory,
    InputList, validate_input_and_determine_scheduler_mode, scale_input_time,
    QueueLevel, JobPool, STSAlgo, LTSAlgo
)

@dataclass
class Scheduler:
    input_data_list: InputList
    cs: int
    half_cs: float = field(init=False)
    q: int
    mode: SchedulerMode
    logs: List[SimulationLog] = field(init=False, default_factory=list)
    current_time: int = 0 # in tick
    def __post_init__(self) -> None:
        """
        Initializes the scheduler
        """
        self.half_cs: int = self.cs/2 
        self.input_data_list.sort(key=lambda x: x[0]) # sorted based on the at
        self.all_algorithms = {
            # Non-preemptive
            "FCFS": self.FCFS,
            "SPN": self.SPN,
            "HRRN": self.HRRN,
            "SRTF": self.SRTF,
            # Preemptive
            "RR": self.RR,
            "MLQ": self.MLQ,
            "MLFQ": self.MLFQ,
            # Job
            "SJF":  self.SJF,
            "FIFO":   self.FIFO,
            "Random":   self.Random
        }
        # self.in_switch = False
        # self.switch_phase = None  # "save" or "load"
        # self.switch_remaining = 0  # Incremented each tick during CS
        # self.outgoing_process = None  # For save phase

    def run(self, algo: Union[LTSAlgo,STSAlgo, None]) -> None:
        """
        Main driver: runs specific algorithms based on the detected SchedulerMode.
        """
        if algo is None:
            algorithms = []
            if self.mode is SchedulerMode.PROCESS:
                algorithms = ["FCFS", "SPN", "HRRN", "RR", "SRTF", "MLFQ"]
            elif self.mode is SchedulerMode.MLQ:
                algorithms = ["MLQ"]
            elif self.mode is SchedulerMode.JOB:
                algorithms = ["FIFO", "SJF", "Random"]
            for algo in algorithms:
                self.all_algorithms[algo]() # Clean dynamic call
        else:
            self.all_algorithms[algo]() # Clean dynamic call

        self.generate_gantt_and_metrics()
        print(self.logs)

    # ===== PROCESS scheduling =====
    def FCFS(self):
        print(f"Running Algorithm: FCFS...")
        # --- Initialization ---
        self._reset_simulation_objects()
        system_state = SystemState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        # CS Tracking
        cs_progress = 0
        # Quantum Tracking
        current_quantum_counter = 0
        # Logging Pointers
        segment_start_time = 0
        next_arrival_idx = 0
        completed_count = 0
        total_data_items = len(self.input_data_list)
        
        # ready queue
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=None, # non-Preemptive logic
                algo="FCFS",
                queue=[]
            )
        ]
        while completed_count <= total_data_items:
            # 1. Handle Arrivals.
            
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    # add to ready queue
                    ready_queue[0].queue.append(proc)
                    ready_queue[0].new_event_occurred = True
                    proc.process_ready_queue_id = 0
                    next_arrival_idx += 1
                    self._add_log(algo="FCFS", start_time=self.current_time, end_time=self.current_time, id=proc.pid, event_type=EventType.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD:
                cs_progress += TICK
                
                # Check Abort (Preemption during Load)                    
                # We check if there is a BETTER process than the one we are loading, but since FCFS likes those who arrived earlier, the best candidate already chosen! 

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log("FCFS", segment_start_time, self.current_time + TICK, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time + TICK
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0
                    
                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time + TICK
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        current_process.wait_time = current_process.response_time # non-preemptive WT=RT
                        
            elif system_state == SystemState.CS_SAVE:
                cs_progress += TICK
                
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log("FCFS", segment_start_time, self.current_time + TICK, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time + TICK
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time + TICK
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                        # Wait time = Response time, already set.
                    
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE           
            elif system_state is SystemState.EXECUTING:
                current_process.remaining_time -= TICK
                current_quantum_counter += TICK
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log("FCFS", segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0                 
            elif system_state is SystemState.IDLE:            
                candidate: Process = None if len(ready_queue[0].queue) == 0 else ready_queue[0].queue.pop(0) # since input data is already sorted based on at
                if candidate:
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time:
                        self._add_log("FCFS", segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                    
                    current_process = candidate # Removed from queue
                    ready_queue[0].new_event_occurred = False # why? the best candidate is already chosen.

                    system_state = SystemState.CS_LOAD
                    cs_progress = 0

                    
                    continue # as soon as we have a process in the ready queue, we're gonna shift into other system states.       
            # Advance Time
            self.current_time += TICK
            
            # Safety break
            if (system_state == SystemState.IDLE and 
                len(ready_queue[0].queue) == 0 and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break
    def SPN(self): # Shortest Process Next (non‑preemptive SJF)
        print(f"Running Algorithm: SPN...")
        # --- Initialization ---
        self._reset_simulation_objects()
        system_state = SystemState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        # CS Tracking
        cs_progress = 0
        # Quantum Tracking
        current_quantum_counter = 0
        # Logging Pointers
        segment_start_time = 0
        next_arrival_idx = 0
        completed_count = 0
        total_data_items = len(self.input_data_list)
        
        # ready queue
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=None, # Preemptive logic
                algo="SPN",
                queue=[]
            )
        ]
        while completed_count <= total_data_items:
            # 1. Handle Arrivals.
            
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    # add to ready queue
                    ready_queue[0].queue.append(proc)
                    ready_queue[0].new_event_occurred = True
                    proc.process_ready_queue_id = 0
                    next_arrival_idx += 1
                    self._add_log(algo=ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, id=proc.pid, event_type=EventType.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD:
                cs_progress += TICK
                
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. We check if there is a BETTER process than the one we are loading. let's check the event!
                    ready_queue[0].new_event_occurred = False
                    best_candidate_in_queue: Process = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    should_abort = False
                    if best_candidate_in_queue.remaining_time < current_process.remaining_time:
                        should_abort = True
                    if should_abort:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_ABORT")
                        segment_start_time = self.current_time
                        
                    
                        current_process.state = ProcessState.READY
                        ready_queue[0].queue.append(current_process)
                        current_process = None
                        
                        system_state = SystemState.IDLE
                        cs_progress = 0
                        continue # freeze time

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time + TICK
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0
                    
                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time + TICK
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        current_process.wait_time = current_process.response_time # non-preemptive WT=RT
                        
            elif system_state == SystemState.CS_SAVE:
                cs_progress += TICK
                
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time + TICK
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time + TICK
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                        # Wait time = Response time, already set.
                    
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE           
            elif system_state is SystemState.EXECUTING: # non-preemptive execution
                current_process.remaining_time -= TICK
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0                 
            elif system_state is SystemState.IDLE:            
                candidate: Process = None if len(ready_queue[0].queue) == 0 else min(ready_queue[0].queue, key=lambda p: p.remaining_time) # since input data is already sorted based on at

                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                    
                    ready_queue[0].queue.remove(candidate)
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False
                    
                    continue # as soon as we have a process in the ready queue, we're gonna shift into other system states.       
            # Advance Time
            self.current_time += TICK
            
            # Safety break
            if (system_state == SystemState.IDLE and 
                len(ready_queue[0].queue) == 0 and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break

    def HRRN(self): # Highest Response Ratio Next
        print(f"Running Algorithm: HRRN...")
        # --- Initialization ---
        self._reset_simulation_objects()
        system_state = SystemState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        # CS Tracking
        cs_progress = 0
        # Quantum Tracking
        current_quantum_counter = 0
        # Logging Pointers
        segment_start_time = 0
        next_arrival_idx = 0
        completed_count = 0
        total_data_items = len(self.input_data_list)
        
        # ready queue
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=None, # Preemptive logic
                algo="HRRN",
                queue=[]
            )
        ]
        while completed_count <= total_data_items:
            # 1. Handle Arrivals.
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    # add to ready queue
                    ready_queue[0].queue.append(proc)
                    ready_queue[0].new_event_occurred = True
                    proc.process_ready_queue_id = 0
                    next_arrival_idx += 1
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, id=proc.pid, event_type=EventType.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD:
                cs_progress += TICK
                # We need to check the ready queue every moment! since, at arrival times, waiting time values are equal to zero but one tick later? how about two ticks later? so we need to check it as long as the ready queue is not empty–this might be a bit overdoing, but it's safe.
                if len(ready_queue[0].queue) > 0: 
                    best_candidate_in_queue: Process = max(ready_queue[0].queue, key=lambda p: (self.current_time - p.arrival_time)/p.burst_time)
                    # ready_queue[0].new_event_occurred = False # not useful anymore! 
                    should_abort = False
                    if (self.current_time - best_candidate_in_queue.arrival_time)/best_candidate_in_queue.burst_time > (self.current_time - current_process.arrival_time)/current_process.burst_time: # higher Response Ratio?
                        should_abort = True
                    if should_abort:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_ABORT")
                        segment_start_time = self.current_time
                        
                    
                        current_process.state = ProcessState.READY
                        ready_queue[0].queue.append(current_process)
                        current_process = None
                        
                        system_state = SystemState.IDLE
                        cs_progress = 0
                        continue # freeze time

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time + TICK
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0
                    
                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time + TICK
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        current_process.wait_time = current_process.response_time # non-preemptive WT=RT
                        
            elif system_state == SystemState.CS_SAVE:
                cs_progress += TICK
                
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time + TICK
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time + TICK
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                        # Wait time = Response time, already set.
                    
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE           
            elif system_state is SystemState.EXECUTING: # non-preemptive execution
                current_process.remaining_time -= TICK
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0                 
            elif system_state is SystemState.IDLE:            
                candidate: Process = None if len(ready_queue[0].queue) == 0 else max(ready_queue[0].queue, key=lambda p: (self.current_time - p.arrival_time)/p.burst_time) # since HRRN is non-preemptive, and every process in the ready queue was waiting from its arrival time, so the waiting time for them is equal to current time - arrival time.

                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                    
                    ready_queue[0].queue.remove(candidate)
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen.
                    
                    continue # as soon as we have a process in the ready queue, we're gonna shift into other system states.       
            # Advance Time
            self.current_time += TICK
            
            # Safety break
            if (system_state == SystemState.IDLE and 
                len(ready_queue[0].queue) == 0 and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break

    def RR(self): # Round Robin
        print(f"Running Algorithm: RR...")
        # --- Initialization ---
        self._reset_simulation_objects()
        system_state = SystemState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        # CS Tracking
        cs_progress = 0
        # Quantum Tracking
        current_quantum_counter = 0
        # Logging Pointers
        segment_start_time = 0
        next_arrival_idx = 0
        completed_count = 0
        total_data_items = len(self.input_data_list)
        
        # ready queue
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=self.q, # Preemptive logic
                algo="RR",
                queue=[]
            )
        ]
        while completed_count <= total_data_items:
            # 1. Handle Arrivals.
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    # add to ready queue
                    ready_queue[0].queue.append(proc)
                    ready_queue[0].new_event_occurred = True
                    proc.process_ready_queue_id = 0
                    next_arrival_idx += 1
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, id=proc.pid, event_type=EventType.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD:
                cs_progress += TICK
                if ready_queue[0].new_event_occurred: # a new process just arrived? okay, we don't care since the RR use the same policy as the FCFS. 
                    pass

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time + TICK
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    
                    
                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time + TICK
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                        
            elif system_state == SystemState.CS_SAVE:
                cs_progress += TICK
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time + TICK
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time + TICK
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    if outgoing_process.state is ProcessState.READY:
                        ready_queue[0].queue.append(outgoing_process)
                        outgoing_process.wait_time -= TICK
                        
                    
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE           
            elif system_state is SystemState.EXECUTING: # preemptive execution
                current_process.remaining_time -= TICK
                current_quantum_counter += TICK
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                elif current_quantum_counter >= self.q:  # quantum time expired?
                    # Log preemption
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    # Ready for CS_save?
                    current_process.state = ProcessState.READY # append ready queue!
                    outgoing_process = current_process
                    current_process = None
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    current_quantum_counter = 0
                
                
                
            elif system_state is SystemState.IDLE:
                candidate: Process = None if len(ready_queue[0].queue) == 0 else ready_queue[0].queue.pop(0) # since input data is already sorted based on at.
                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    # ready_queue[0].queue.remove(candidate) # Not useful here, since we already popped the candidate!
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue      
            # Advance Time
            for p in ready_queue[0].queue:
                p.wait_time += TICK
                
            self.current_time += TICK
            # Safety break
            if (system_state == SystemState.IDLE and 
                len(ready_queue[0].queue) == 0 and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break


    def SRTF(self): # Shortest Remaining Time First
        print(f"Running Algorithm: SRTF...")
        # --- Initialization ---
        self._reset_simulation_objects()
        system_state = SystemState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        # CS Tracking
        cs_progress = 0
        # Quantum Tracking
        current_quantum_counter = 0
        # Logging Pointers
        segment_start_time = 0
        next_arrival_idx = 0
        completed_count = 0
        total_data_items = len(self.input_data_list)
        
        # ready queue
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=self.q, # Preemptive logic
                algo="SRTF",
                queue=[]
            )
        ]
        while completed_count <= total_data_items:
            # 1. Handle Arrivals.
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    # add to ready queue
                    ready_queue[0].queue.append(proc)
                    ready_queue[0].new_event_occurred = True
                    proc.process_ready_queue_id = 0
                    next_arrival_idx += 1
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, id=proc.pid, event_type=EventType.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD:
                cs_progress += TICK
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. We check if there is a BETTER process than the one we are loading. let's check the event!
                    ready_queue[0].new_event_occurred = False
                    best_candidate_in_queue: Process = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    should_abort = False
                    if best_candidate_in_queue.remaining_time < current_process.remaining_time:
                        should_abort = True
                    if should_abort:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_ABORT")
                        segment_start_time = self.current_time
                        
                    
                        current_process.state = ProcessState.READY
                        ready_queue[0].queue.append(current_process)
                        current_process = None
                        
                        system_state = SystemState.IDLE
                        cs_progress = 0
                        continue # freeze time

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time + TICK
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    
                    
                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time + TICK
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                        
            elif system_state == SystemState.CS_SAVE:
                cs_progress += TICK
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time + TICK
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time + TICK
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    if outgoing_process.state is ProcessState.READY:
                        ready_queue[0].queue.append(outgoing_process)
                        outgoing_process.wait_time -= TICK
                        
                    
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE           
            elif system_state is SystemState.EXECUTING: # preemptive execution
                current_process.remaining_time -= TICK
                current_quantum_counter += TICK
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                elif current_quantum_counter >= self.q:  # quantum time expired?
                    # Log quantum time expired
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time + TICK
                    
                    # Ready for CS_save?
                    current_process.state = ProcessState.READY # append ready queue!
                    outgoing_process = current_process
                    current_process = None
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    current_quantum_counter = 0
                elif ready_queue[0].new_event_occurred: # that means a new process just arrived. We check if there is a BETTER process than the one we are loading. let's check the event!
                    ready_queue[0].new_event_occurred = False
                    best_candidate_in_queue: Process = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    should_abort = False
                    if best_candidate_in_queue.remaining_time < current_process.remaining_time+1:
                        should_abort = True
                    if should_abort:
                        print(self.current_time)
                        print(current_process)
                        print("\n")
                        print(best_candidate_in_queue)
                        exit()
                        # Log quantum time expired
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time + TICK, current_process.pid, "EXECUTING")
                        segment_start_time = self.current_time + TICK
                        
                        # Ready for CS_save?
                        current_process.state = ProcessState.READY # append ready queue!
                        outgoing_process = current_process
                        current_process = None
                        system_state = SystemState.CS_SAVE
                        cs_progress = 0
                        current_quantum_counter = 0

                               
            elif system_state is SystemState.IDLE:
                candidate: Process = None if len(ready_queue[0].queue) == 0 else min(ready_queue[0].queue, key=lambda p: p.remaining_time) # since input data is already sorted based on at
                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    ready_queue[0].queue.remove(candidate) # remove the candidate from ready queue!
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue      
            # Advance Time
            for p in ready_queue[0].queue:
                p.wait_time += TICK
                
            self.current_time += TICK
            # Safety break
            if (system_state == SystemState.IDLE and 
                len(ready_queue[0].queue) == 0 and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break


    def MLFQ(self):     # Multi‑Level Feedback Queue
        pass

    # ===== MLQ scheduling =====
    def MLQ(self):
        pass

    # ===== JOB scheduling =====
    def FIFO(self):
        pass

    def SJF(self):
        pass

    def Random(self):
        pass

    # --- Helper Methods ---
    def _reset_simulation_objects(self) -> None:
        """Recreates process/job objects and time for a fresh run."""
        # Reset the self.processes or self.jobs, all of them are already sorted based on at
        if self.mode is SchedulerMode.PROCESS:
            self.processes: List[Process] = []
            for i, (at, cbt) in enumerate(self.input_data_list):
                self.processes.append(Process(pid=i, arrival_time=at, burst_time=cbt))
        elif self.mode is SchedulerMode.JOB: 
            self.jobs: List[Job] = []
            for i, (at, cbt, m) in enumerate(self.input_data_list):
                self.jobs.append(Job(jobId=i, arrival_time=at, burst_time=cbt, memory_needed_kb=m))
        else: # MLQ
            self.processes: List[Process] = []
            for i, (at, cbt, cat) in enumerate(self.input_data_list):
                self.processes.append(Process(pid=i, arrival_time=at, burst_time=cbt, category=cat))
        # reset time
        self.current_time = 0


    def _is_preemptive(self, algo: str) -> bool:
        return algo in ["RR", "SRTF"]

    def _check_preemption(self, current: Process, ready_queue: List[QueueLevel], quantum_used: int, system_state: SystemState) -> bool:
        # quantum time expired? -> SystemState.EXECUTING, current 
        # any process with higher priority arrived? -> SystemState.EXECUTING, current / SystemState.LOAD, current
        if not ready_queue:
            return False
        
        if system_state is SystemState.EXECUTING: # system is executing a process
            if ready_queue[0].q is None: # non-preemptive algorithm
                return False
            else: # preemptive algorithms
                if len(ready_queue) == 1: # one level
                    if ready_queue[0].algo == "RR":
                        return quantum_used >= self.q
                    elif ready_queue[0].algo == "SRTF":
                        # Check if any process in ready queue has strictly lower remaining time
                        shortest_in_queue = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                        return shortest_in_queue.remaining_time < current.remaining_time
                    elif ready_queue[0].algo == "MLFQ": # It could be MLFQ with one level of queues, we used RR for MLFQ
                        return quantum_used >= self.q
                else: #MLFQ with at least two level
                    pass
        
        if system_state is SystemState.CS_LOAD: # override the CPU registers
            if len(ready_queue) == 1: # one level
                if ready_queue[0].algo == "RR":
                        return False
                elif ready_queue[0].algo == "SRTF":
                    # Check if any process in ready queue has strictly lower remaining time
                    shortest_in_queue = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    return shortest_in_queue.remaining_time < current.remaining_time
                elif ready_queue[0].algo == "MLFQ": # It could be MLFQ with one level of queues, used RR for MLFQ, remember there's only one level here
                    return False
            else: #MLFQ with at least two level
                pass
        
        return False

    def _get_hrrn_candidate(self, ready_queue: List[Process], current: int) -> Process:
        # R = (w + s) / s
        best = None
        max_ratio = -1.0
        for p in ready_queue:
            wait = self.current_time - p.arrival_time - (p.burst_time - p.remaining_time)
            # Avoid div by zero if burst is 0 (shouldn't happen)
            ratio = (wait + p.burst_time) / p.burst_time if p.burst_time > 0 else 0
            if ratio > max_ratio:
                max_ratio = ratio
                best = p
        return best

    def _add_log(self, algo: Union[LTSAlgo,STSAlgo], start_time: float, end_time: float, id: Optional[int], event_type: Union[SystemState,EventType]):
        self.logs.append(SimulationLog(algo, start_time, end_time, id, event_type))

    def generate_gantt_and_metrics(self):
        """
        Generates:
        1. Metrics Table (Detailed statistics per process)
        2. Sequential Event Log (Compact, debugging-focused timeline)
        """
        
        # ==========================
        # 1. METRICS TABLE
        # ==========================
        print(f"\n{'='*25} SIMULATION REPORT {'='*25}")
        print(f"{'PID':<5} {'AT':<8} {'BT':<8} {'CT':<8} {'TAT':<8} {'WT':<8} {'RT':<8}")
        print("-" * 65)

        total_tat, total_wt, total_rt = 0, 0, 0
        sorted_processes = sorted(self.processes, key=lambda p: p.pid)
        n = len(sorted_processes)

        for p in sorted_processes:
            # Scale internal ticks back to user time units
            at = p.arrival_time / TIME_SCALE
            bt = p.burst_time / TIME_SCALE
            
            if p.completion_time == -1:
                ct = tat = wt = rt = 0.0
            else:
                ct = p.completion_time / TIME_SCALE
                tat = p.turnaround_time / TIME_SCALE
                wt = p.wait_time / TIME_SCALE
                rt = p.response_time / TIME_SCALE

            total_tat += tat
            total_wt += wt
            total_rt += rt

            print(f"{p.pid:<5} {at:<8.2f} {bt:<8.2f} {ct:<8.2f} {tat:<8.2f} {wt:<8.2f} {rt:<8.2f}")

        if n > 0:
            print("-" * 65)
            print(f"AVG  : {'-':<8} {'-':<8} {'-':<8} {total_tat/n:<8.2f} {total_wt/n:<8.2f} {total_rt/n:<8.2f}")


        # ==========================
        # 2. SEQUENTIAL EVENT LOG (DEBUG VIEW)
        # ==========================
        print("\n\n[ Event Sequence Debugger ]")
        print("Format: EventType(Start-End)  |  '->' implies sequence order, not time gap.")
        print("-" * 80)
        
        if not self.logs:
            print("No logs available.")
            return

        # Helper to format time cleanly (e.g., 5.0 -> 5)
        def fmt(t):
            val = t / TIME_SCALE
            return f"{val:.0f}" if val.is_integer() else f"{val:.2f}"

        # 1. Collect all events per process
        # We store tuples: (start_time, priority_order, string_label)
        # priority_order ensures Arrival (0) appears before Execution (1) if they happen at same tick.
        process_events = {p.pid: [] for p in self.processes}

        # Add Arrivals
        for p in self.processes:
            label = f"AT({fmt(p.arrival_time)})"
            # Priority 0: Arrivals come first
            process_events[p.pid].append((p.arrival_time, 0, label))

        # Add Simulation Logs
        for log in self.logs:
            if log.id is None: continue # Skip idle
            if log.start_time == log.end_time: continue # Skip instantaneous system events

            s_str = fmt(log.start_time)
            e_str = fmt(log.end_time)

            if log.event_type == 'EXECUTING':
                lbl = f"Exec({s_str}-{e_str})"
            elif 'CS_LOAD' in log.event_type:
                lbl = f"Load({s_str}-{e_str})"
            elif 'CS_SAVE' in log.event_type:
                lbl = f"Save({s_str}-{e_str})"
            else:
                lbl = f"{log.event_type}({s_str}-{e_str})"
            
            # Priority 1: Regular events
            process_events[log.id].append((log.start_time, 1, lbl))

        # 2. Sort and Print
        for pid in sorted(process_events.keys()):
            # Sort by Start Time, then Priority
            events = sorted(process_events[pid], key=lambda x: (x[0], x[1]))
            
            # Extract just the labels
            event_labels = [e[2] for e in events]
            
            # Join with arrow
            timeline_str = " -> ".join(event_labels)
            
            print(f"P{pid:<3} : {timeline_str}")


input_list: InputList = [[9, 1], [0, 7], [21, 6], [20, 11]] # 2,9 / 3,25 / 6, 1 / 10,7
input_quantum_time: float = 5
input_cs_time: float = 2

## Input Validation
scheduler_mode: SchedulerMode = validate_input_and_determine_scheduler_mode(data_list=input_list, q=input_quantum_time, cs=input_cs_time)
(data_list_scaled, q_scaled, cs_scaled) = scale_input_time(data_list=input_list, q=input_quantum_time, cs=input_cs_time, scheduler_mode=scheduler_mode, max_precision=4)


# Scheduling
scheduler = Scheduler(data_list_scaled, cs_scaled, q_scaled, scheduler_mode)
scheduler.run("RR")

# Visualization

