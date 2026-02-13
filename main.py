# import bpy
# import sys

# # --- HELPER FUNCTION TO RELOAD BLENDER TEXT BLOCKS ---
# def require(module_name):
#     """
#     Reloads a Blender text block as a module and updates sys.modules.
#     Use this before importing local scripts.
#     """
#     filename = module_name + ".py"
    
#     # 1. Force Python to forget the old version
#     if module_name in sys.modules:
#         del sys.modules[module_name]
        
#     # 2. Re-compile the text block
#     if filename in bpy.data.texts:
#         mod = bpy.data.texts[filename].as_module()
#         sys.modules[module_name] = mod
#     else:
#         raise ImportError(f"❌ '{filename}' not found in Blender Text Editor!")

# # =========================================================
# # 1. LOAD DEPENDENCIES (Order Matters!)
# # =========================================================

# # Load 'definitions' first because everyone uses it
# require("definitions")

# # Load 'BlenderCode' next
# require("BlenderCode")

# # =========================================================
# # 2. NOW IMPORT NORMALLY
# # =========================================================

from typing import Union, List, Optional
from dataclasses import dataclass, field
# import BlenderCode
from definitions import (
    TICK,
    SimulationLog, SystemState, SchedulerMode, ProcessEvents,
    Process, ProcessState, ProcessCategory,
    InputList, validate_input_and_determine_scheduler_mode, scale_input_time,
    QueueLevel, STSAlgo
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
            "MLQ": self.MLQ, # + category
            "MLFQ": self.MLFQ
        }

    def run(self, algo: STSAlgo) -> None:
        """
        Main driver: runs specific algorithm
        """
        available_algorithms = []
        if self.mode is SchedulerMode.STANDARD:
            available_algorithms = ["FCFS", "SPN", "HRRN", "RR", "SRTF", "MLFQ"]
        elif self.mode is SchedulerMode.MLQ:
            available_algorithms = ["MLQ"]


        if algo not in available_algorithms:
            raise ValueError(f"The selected algorithm ({algo}) isn't compatible with the input_data format!\nAvailable algorithms: {', '.join(available_algorithms)}")

        self.all_algorithms[algo]() # Clean dynamic call

        self.generate_gantt_and_metrics()

    # ===== STANDARD scheduling =====

    def FCFS(self): # First-come, First-serve
        print(f"Running Algorithm: FCFS...")
        # --- Initialization ---
        self._reset_simulation_objects()
        system_state = SystemState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        # CS Tracking
        cs_progress = 0
        # # Quantum Tracking
        # current_quantum_counter = 0
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
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                if ready_queue[0].new_event_occurred: # a new process just arrived? okay, we don't care since the FCFS doesn't care :)
                    pass
                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    # current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time
                    # outgoing_process.state is ProcessState.TERMINATED:
                    outgoing_process.completion_time = self.current_time
                    outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    outgoing_process = None
                    cs_progress = 0
                    
                    system_state = SystemState.IDLE
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # non-preemptive execution
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. But we don't care :)
                    pass
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                               
            elif system_state is SystemState.IDLE:
                candidate: Process | None = None if len(ready_queue[0].queue) == 0 else ready_queue[0].queue.pop(0) # since input data is already sorted based on at.
                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
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
 
    def SPN(self): # Shortest Process Next 
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
                q=None, # non-Preemptive logic
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
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. We check if there is a BETTER process than the one we are loading. let's check the event!
                    ready_queue[0].new_event_occurred = False
                    best_candidate_in_queue: Process = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    if best_candidate_in_queue.remaining_time < current_process.remaining_time:
                        # should_abort = True
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                        segment_start_time = self.current_time
                        
                    
                        current_process.state = ProcessState.READY
                        ready_queue[0].queue.append(current_process)
                        current_process = None
                        system_state = SystemState.IDLE
                        cs_progress = 0
                        continue # no ticks!
                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time
                    # outgoing_process.state is ProcessState.TERMINATED:
                    outgoing_process.completion_time = self.current_time
                    outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # non-preemptive execution
                if ready_queue[0].new_event_occurred:
                    pass
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    # current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                               
            elif system_state is SystemState.IDLE:
                candidate: Process | None = None if len(ready_queue[0].queue) == 0 else min(ready_queue[0].queue, key=lambda p: p.remaining_time) 
                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    ready_queue[0].queue.remove(candidate) # remove the candidate from ready queue!
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
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


    def HRRN(self): # Highest Response Ration First
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
                q=None, # non-Preemptive logic
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
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                if len(ready_queue[0].queue) > 0: # We need to check the ready queue every ticks! since, at arrival times, waiting time values are equal to zero but one tick later? how about two ticks later? so we need to check it as long as the ready queue is not empty–this might be a bit overdoing, but it's safe.
                    best_candidate_in_queue: Process = max(ready_queue[0].queue, key=lambda p: (p.wait_time)/p.burst_time)
                    # should_abort = False
                    if (best_candidate_in_queue.wait_time)/best_candidate_in_queue.burst_time > (current_process.wait_time)/current_process.burst_time:
                        # should_abort = True
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                        segment_start_time = self.current_time
                        
                    
                        current_process.state = ProcessState.READY
                        ready_queue[0].queue.append(current_process)
                        current_process = None
                        system_state = SystemState.IDLE
                        cs_progress = 0
                        continue # no ticks!
                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time
                  
                    # Outgoing process was terminated!
                    outgoing_process.completion_time = self.current_time
                    outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    
                    outgoing_process = None
                    cs_progress = 0
                    system_state = SystemState.IDLE # we're gonna select the next candidate if there's any!
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # non-preemptive execution
                if ready_queue[0].new_event_occurred: # non-preemptive, so we don't look at the ready queue anymore.
                    pass
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                               
            elif system_state is SystemState.IDLE:
                candidate: Process | None = None if len(ready_queue[0].queue) == 0 else max(ready_queue[0].queue, key=lambda p: (p.wait_time)/p.burst_time) # since HRRN is non-preemptive, and every process in the ready queue was waiting from its arrival time, so the waiting time for them is equal to current time - arrival time.                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    ready_queue[0].queue.remove(candidate) # remove the candidate from ready queue!
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
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
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                if ready_queue[0].new_event_occurred: # a new process just arrived? okay, we don't care since the RR use the same policy as the FCFS.
                    pass
                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    elif outgoing_process.state is ProcessState.READY:
                        ready_queue[0].queue.append(outgoing_process)
                    outgoing_process = None
                    cs_progress = 0
                    
                    system_state = SystemState.IDLE
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # preemptive execution
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. But we don't care :)
                    pass
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                elif current_quantum_counter >= self.q:  # quantum time expired?
                    # Log quantum time expired
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    # Ready for CS_save?
                    current_process.state = ProcessState.READY # append ready queue in CS_Save!
                    outgoing_process = current_process
                    current_process = None
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    current_quantum_counter = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                current_quantum_counter += TICK
                               
            elif system_state is SystemState.IDLE:
                candidate: Process | None = None if len(ready_queue[0].queue) == 0 else ready_queue[0].queue.pop(0) # since input data is already sorted based on at.
                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
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
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. We check if there is a BETTER process than the one we are loading. let's check the event!
                    ready_queue[0].new_event_occurred = False
                    best_candidate_in_queue: Process = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    should_abort = False
                    if best_candidate_in_queue.remaining_time < current_process.remaining_time:
                        should_abort = True
                    if should_abort:
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                        segment_start_time = self.current_time
                        
                    
                        current_process.state = ProcessState.READY
                        ready_queue[0].queue.append(current_process)
                        current_process = None
                        system_state = SystemState.IDLE
                        cs_progress = 0
                        continue # no ticks!
                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:
                    # Save Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time
                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    elif outgoing_process.state is ProcessState.READY:
                        ready_queue[0].queue.append(outgoing_process)
                    outgoing_process = None
                    cs_progress = 0
                    # Here we need to do something so in the next loop, we're gonna select the next candidate!
                    system_state = SystemState.IDLE
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # preemptive execution
                if ready_queue[0].new_event_occurred: # that means a new process just arrived. We check if there is a BETTER process than the one we are loading. let's check the event!
                    ready_queue[0].new_event_occurred = False
                    best_candidate_in_queue: Process = min(ready_queue[0].queue, key=lambda p: p.remaining_time)
                    if best_candidate_in_queue.remaining_time < current_process.remaining_time:
                            # Log quantum time expired
                            self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                            segment_start_time = self.current_time
                            
                            # Ready for CS_save?
                            current_process.state = ProcessState.READY # append ready queue!
                            outgoing_process = current_process
                            current_process = None
                            
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                            current_quantum_counter = 0
                            continue # no ticks!
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                elif current_quantum_counter >= self.q:  # quantum time expired?
                    # Log quantum time expired
                    self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    # Ready for CS_save?
                    current_process.state = ProcessState.READY # append ready queue!
                    outgoing_process = current_process
                    current_process = None
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    current_quantum_counter = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                current_quantum_counter += TICK
                               
            elif system_state is SystemState.IDLE:
                candidate: Process | None = None if len(ready_queue[0].queue) == 0 else min(ready_queue[0].queue, key=lambda p: p.remaining_time) 
                
                if candidate:
                    
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[0].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    ready_queue[0].queue.remove(candidate) # remove the candidate from ready queue!
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[0].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
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
        # At most we have four queues, which they are generated only if needed(automatically).
        ## First queue: RR, q=self.q
        ## Second queue: RR, q=self.q*2
        ## Third queue: RR, q=self.q*3
        ## Fourth queue: FCFS
        print(f"Running Algorithm: MLFQ...")
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
        
        
        # ready queues
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=self.q*1, # Preemptive logic
                algo="RR",
                queue=[]
            )
            # QueueLevel(
            #     q=self.q*2, # Preemptive logic
            #     algo="RR",
            #     queue=[]
            # ),
            # QueueLevel(
            #     q=self.q*3, # Preemptive logic
            #     algo="RR",
            #     queue=[]
            # ),
            # QueueLevel(
            #     q=None, # non-Preemptive logic
            #     algo="FCFS",
            #     queue=[]
            # )
        ]

        while completed_count <= total_data_items:
            # 1. Handle Arrivals (append to the first queue).
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    # add to ready queue
                    ready_queue[0].queue.append(proc)
                    ready_queue[0].new_event_occurred = True
                    proc.process_ready_queue_id = 0
                    next_arrival_idx += 1
                    self._add_log(ready_queue[0].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                # a new process just arrived at a queue with a higher level than the current process?
                best_candidate_in_queue = None
                for i, queue_level in enumerate(ready_queue):
                    if queue_level.new_event_occurred and i < current_process.process_ready_queue_id:
                        queue_level.new_event_occurred = False
                        best_candidate_in_queue = None if len(queue_level.queue) == 0 else queue_level.queue[0] # since input data is already sorted based on at.
                        if best_candidate_in_queue:
                                break
                
                if best_candidate_in_queue and best_candidate_in_queue.process_ready_queue_id < current_process.process_ready_queue_id:
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.READY
                    ready_queue[current_process.process_ready_queue_id].queue.append(current_process)
                    current_process = None
                    system_state = SystemState.IDLE
                    cs_progress = 0
                    continue # no ticks!

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:

                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    elif outgoing_process.state is ProcessState.READY:
                        # outgoing_process.process_ready_queue_id could be 1, 2, 3
                        if outgoing_process.process_ready_queue_id >= len(ready_queue): # Create a new queue level
                            if outgoing_process.process_ready_queue_id == 3: # is it the last level (FCFS)?
                                ready_queue.append(
                                    QueueLevel(
                                        algo="FCFS",
                                        q=None,
                                        queue=[]
                                    )
                                )
                            else: 
                                ready_queue.append(
                                    QueueLevel(
                                        algo="RR",
                                        q=self.q*(outgoing_process.process_ready_queue_id+1),
                                        queue=[]
                                    )
                                )
                        ready_queue[outgoing_process.process_ready_queue_id].queue.append(outgoing_process)
                        
                    # Save Complete
                    self._add_log(ready_queue[outgoing_process.process_ready_queue_id].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time          
                    outgoing_process = None
                    cs_progress = 0
                    
                    system_state = SystemState.IDLE
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # preemptive + non-preemptive execution
                if ready_queue[current_process.process_ready_queue_id].algo == "FCFS": # non-preemptive
                    pass
                else: # FIFO: queue_level could be 0, 1, 2
                    # a new process just arrived at a queue with a higher level than the current process?
                    best_candidate_in_queue = None
                    for i, queue_level in enumerate(ready_queue):
                        if queue_level.new_event_occurred and i < current_process.process_ready_queue_id:
                            best_candidate_in_queue = None if len(queue_level.queue) == 0 else queue_level.queue[0] # since input data is already sorted based on at.
                            queue_level.new_event_occurred = False
                            if best_candidate_in_queue:
                                break
                    if best_candidate_in_queue and best_candidate_in_queue.process_ready_queue_id < current_process.process_ready_queue_id:
                        self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                        segment_start_time = self.current_time
                        
                        # Ready for CS_save?
                        current_process.state = ProcessState.READY # append ready queue!
                        outgoing_process = current_process
                        current_process = None
                        
                        system_state = SystemState.CS_SAVE
                        current_quantum_counter = 0
                        cs_progress = 0
                        continue # no ticks!
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                elif ready_queue[current_process.process_ready_queue_id].algo == "RR" and current_quantum_counter >= ready_queue[current_process.process_ready_queue_id].q:  # quantum time expired? Only Preemptive Queue levels.
                    # Log quantum time expired
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    # Ready for CS_save?
                    current_process.state = ProcessState.READY # append  to the next ready queue in CS_Save!
                    current_process.process_ready_queue_id+=1 # here's the thing.
                    outgoing_process = current_process
                    current_process = None
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    current_quantum_counter = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                if ready_queue[current_process.process_ready_queue_id].algo == "RR":
                    current_quantum_counter += TICK
                               
            elif system_state is SystemState.IDLE:
                for queue_level in ready_queue: # Iterate through queues in order of priority
                    candidate: Process = None if len(queue_level.queue) == 0 else queue_level.queue.pop(0) # since input data is already sorted based on at.
                    if candidate:
                        break
                
                if candidate:
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[candidate.process_ready_queue_id].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[current_process.process_ready_queue_id].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
            # Advance Time
            
            for queue_level in ready_queue:
                for p in queue_level.queue:
                    p.wait_time += TICK # add waiting time to all processes in all queues.
                
            self.current_time += TICK
            # Safety break
            ## Check if every queue list is empty
            are_all_queues_empty = all(len(queue_level.queue) == 0 for queue_level in ready_queue)
            if (system_state == SystemState.IDLE and 
                are_all_queues_empty and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break


    # ===== MLQ scheduling =====
    def MLQ(self):     # Multi‑Level Queue 
        # At most we have four queues, which they are generated only if needed(automatically).
        ## First queue: REAL TIME,RR, q=self.q
        ## Second queue: SYSTEM, SPN , q=self.q*2
        ## Third queue: INTERACTIVE, FF RR, q=self.q*3
        ## Fourth queue: FCFS
        print(f"Running Algorithm: MLQ...")
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
        
        
        # ready queues
        ready_queue: List[QueueLevel] = [
            QueueLevel(
                q=self.q*1, # Preemptive logic
                algo="RR",
                queue=[]
            ),
            QueueLevel(
                q=self.q*2, # Preemptive logic
                algo="SPN",
                queue=[]
            ),
            QueueLevel(
                q=self.q*3, # Preemptive logic
                algo="RR",
                queue=[]
            ),
            QueueLevel(
                q=None, # non-Preemptive logic
                algo="FCFS",
                queue=[]
            )
        ]

        while completed_count <= total_data_items:
            # 1. Handle Arrivals (append to the first queue).
            while next_arrival_idx < total_data_items:
                proc = self.processes[next_arrival_idx]
                if proc.arrival_time <= self.current_time:
                    proc.state = ProcessState.READY
                    
                    # add to ready queue
                    if proc.category == ProcessCategory.REAL_TIME.value: # 0, RR
                        ready_queue[0].queue.append(proc)
                        ready_queue[0].new_event_occurred = True
                        proc.process_ready_queue_id = 0
                    elif proc.category == ProcessCategory.SYSTEM.value: # 1, SPN
                        ready_queue[1].queue.append(proc)
                        ready_queue[1].new_event_occurred = True
                        proc.process_ready_queue_id = 1
                    elif proc.category == ProcessCategory.INTERACTIVE.value: # 2, RR
                        ready_queue[2].queue.append(proc)
                        ready_queue[2].new_event_occurred = True
                        proc.process_ready_queue_id = 2
                    elif proc.category == ProcessCategory.BATCH.value: # 3, FCFS
                        ready_queue[3].queue.append(proc)
                        ready_queue[3].new_event_occurred = True
                        proc.process_ready_queue_id = 3
    
                    next_arrival_idx += 1
                    self._add_log(ready_queue[proc.process_ready_queue_id].algo, start_time=self.current_time, end_time=self.current_time, pid=proc.pid, event_type=ProcessEvents.PROCESS_ARRIVAL.value)
                else:
                    break
            

            if system_state == SystemState.CS_LOAD: 
                # a new process just arrived at a queue with a higher level than the current process?
                best_candidate_in_queue = None
                for i, queue_level in enumerate(ready_queue):
                    if queue_level.new_event_occurred and i < current_process.process_ready_queue_id:
                        queue_level.new_event_occurred = False
                        best_candidate_in_queue = None if len(queue_level.queue) == 0 else queue_level.queue[0] # since input data is already sorted based on at.
                        if best_candidate_in_queue:
                                break
                
                if best_candidate_in_queue and best_candidate_in_queue.process_ready_queue_id < current_process.process_ready_queue_id:
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.READY
                    ready_queue[current_process.process_ready_queue_id].queue.append(current_process)
                    current_process = None
                    system_state = SystemState.IDLE
                    cs_progress = 0
                    continue # no ticks!

                if cs_progress >= self.half_cs:
                    # Load Complete
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "CS_LOAD")
                    segment_start_time = self.current_time
                    
                    system_state = SystemState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    cs_progress = 0

                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = self.current_time
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        # current_process.wait_time = current_process.response_time # preemptive WT≠RT
                    continue # no ticks!
                cs_progress += TICK    
            elif system_state == SystemState.CS_SAVE:
                if cs_progress >= self.half_cs:

                    if outgoing_process.state is ProcessState.TERMINATED:
                        outgoing_process.completion_time = self.current_time
                        outgoing_process.turnaround_time = outgoing_process.completion_time - outgoing_process.arrival_time
                    elif outgoing_process.state is ProcessState.READY:
                        # outgoing_process.process_ready_queue_id could be 1, 2, 3
                        if outgoing_process.process_ready_queue_id >= len(ready_queue): # Create a new queue level
                            if outgoing_process.process_ready_queue_id == 3: # is it the last level (FCFS)?
                                ready_queue.append(
                                    QueueLevel(
                                        algo="FCFS",
                                        q=None,
                                        queue=[]
                                    )
                                )
                            else: 
                                ready_queue.append(
                                    QueueLevel(
                                        algo="RR",
                                        q=self.q*(outgoing_process.process_ready_queue_id+1),
                                        queue=[]
                                    )
                                )
                        ready_queue[outgoing_process.process_ready_queue_id].queue.append(outgoing_process)
                        
                    # Save Complete
                    self._add_log(ready_queue[outgoing_process.process_ready_queue_id].algo, segment_start_time, self.current_time, outgoing_process.pid, "CS_SAVE")
                    segment_start_time = self.current_time          
                    outgoing_process = None
                    cs_progress = 0
                    
                    system_state = SystemState.IDLE
                    continue # no ticks!
                cs_progress += TICK
            elif system_state is SystemState.EXECUTING: # preemptive + non-preemptive execution
                if ready_queue[current_process.process_ready_queue_id].algo == "FCFS": # non-preemptive
                    pass
                else: # FIFO: queue_level could be 0, 1, 2
                    # a new process just arrived at a queue with a higher level than the current process?
                    best_candidate_in_queue = None
                    for i, queue_level in enumerate(ready_queue):
                        if queue_level.new_event_occurred and i < current_process.process_ready_queue_id:
                            best_candidate_in_queue = None if len(queue_level.queue) == 0 else queue_level.queue[0] # since input data is already sorted based on at.
                            queue_level.new_event_occurred = False
                            if best_candidate_in_queue:
                                break
                    if best_candidate_in_queue and best_candidate_in_queue.process_ready_queue_id < current_process.process_ready_queue_id:
                        self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                        segment_start_time = self.current_time
                        
                        # Ready for CS_save?
                        current_process.state = ProcessState.READY # append ready queue!
                        outgoing_process = current_process
                        current_process = None
                        
                        system_state = SystemState.CS_SAVE
                        current_quantum_counter = 0
                        cs_progress = 0
                        continue # no ticks!
                
                if current_process.remaining_time <= 0: # terminated
                    # Burst Complete
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    
                    outgoing_process = current_process
                    current_process = None
                    current_quantum_counter = 0
                    
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    continue # no ticks!
                elif ready_queue[current_process.process_ready_queue_id].algo == "RR" and current_quantum_counter >= ready_queue[current_process.process_ready_queue_id].q:  # quantum time expired? Only Preemptive Queue levels.
                    # Log quantum time expired
                    self._add_log(ready_queue[current_process.process_ready_queue_id].algo, segment_start_time, self.current_time, current_process.pid, "EXECUTING")
                    segment_start_time = self.current_time
                    
                    # Ready for CS_save?
                    current_process.state = ProcessState.READY # append  to the next ready queue in CS_Save!
                    current_process.process_ready_queue_id+=1 # here's the thing.
                    outgoing_process = current_process
                    current_process = None
                    system_state = SystemState.CS_SAVE
                    cs_progress = 0
                    current_quantum_counter = 0
                    continue # no ticks!
                current_process.remaining_time -= TICK
                if ready_queue[current_process.process_ready_queue_id].algo == "RR":
                    current_quantum_counter += TICK
                               
            elif system_state is SystemState.IDLE: # Iterate through queues in order of priority
                candidate = None
                if len(ready_queue[0].queue) != 0: # RR, 0, real-time
                    candidate: Process | None = None if len(ready_queue[0].queue) == 0 else ready_queue[0].queue[0] # since input data is already sorted based on at.  
                elif len(ready_queue[1].queue) != 0: # SPN, 0, system
                    candidate: Process = None if len(ready_queue[1].queue) == 0 else min(ready_queue[1].queue, key=lambda p: p.remaining_time)
                elif len(ready_queue[2].queue) != 0: # RR, 0, realtime
                    candidate: Process | None = None if len(ready_queue[2].queue.queue) == 0 else ready_queue[2].queue.queue[0] # since input data is already sorted based on at.
                elif len(ready_queue[3].queue) != 0: # FCFS, 3, batch
                    candidate: Process | None = None if len(ready_queue[3].queue) == 0 else ready_queue[3].queue[0] # since input data is already sorted based on at.
                    
                
                if candidate:
                    # Log IDLE time if we were waiting
                    if self.current_time > segment_start_time: # avoid logging on 0 if a process arrived at 0 and system was idle(situations like: system is idle, but it switches into other states instantly, no ticks)
                        self._add_log(ready_queue[candidate.process_ready_queue_id].algo, segment_start_time, self.current_time, None, "IDLE")
                        segment_start_time = self.current_time
                        
                    ready_queue[candidate.process_ready_queue_id].remov
                    current_process = candidate # Removed from queue
                    system_state = SystemState.CS_LOAD
                    cs_progress = 0
                    ready_queue[current_process.process_ready_queue_id].new_event_occurred = False # Since the best candidate till now is already chosen and the time is gonna be frozen for one tick.
                    
                    continue # no ticks!     
            # Advance Time
            
            for queue_level in ready_queue:
                for p in queue_level.queue:
                    p.wait_time += TICK # add waiting time to all processes in all queues.
                
            self.current_time += TICK
            # Safety break
            ## Check if every queue list is empty
            are_all_queues_empty = all(len(queue_level.queue) == 0 for queue_level in ready_queue)
            if (system_state == SystemState.IDLE and 
                are_all_queues_empty and 
                next_arrival_idx >= total_data_items and 
                current_process is None and
                outgoing_process is None):
                break


    # --- Helper Methods ---
    def _reset_simulation_objects(self) -> None:
        """Recreates process objects and time for a fresh run."""
        # Reset the self.processes, all of them are already sorted based on at
        self.processes: List[Process] = []
        if self.mode is SchedulerMode.STANDARD:
            for i, (at, cbt) in enumerate(self.input_data_list):
                self.processes.append(Process(pid=i, arrival_time=at, burst_time=cbt))
        elif self.mode is SchedulerMode.MLQ: 
            for i, (at, cbt, cat) in enumerate(self.input_data_list):
                self.processes.append(Process(pid=i, arrival_time=at, burst_time=cbt, category=cat))
        # reset time
        self.current_time = 0


    def _add_log(self, algo: STSAlgo, start_time: float, end_time: float, pid: Optional[int], event_type: Union[SystemState,ProcessEvents]):
        self.logs.append(SimulationLog(algo, start_time, end_time, pid, event_type))

    def generate_gantt_and_metrics(self):
        """
        Generates:
        1. Metrics Table
        2. gantt chart
        
        Shown Both in Blender, and Terminal as logs
        """        
        # ==========================
        # 0. Helper Functions
        # ==========================
        ## Helper to format time cleanly (e.g., 5.0 -> 5)
        ### If val is a whole number (e.g., 5.0), format as "5", otherwise keep precision (e.g., "5.25").
        def fmt(t, descaling: bool = False) -> str:
            val = t
            if descaling:
                val = t / TIME_SCALE
            return f"{val:.0f}" if val.is_integer() else f"{val:.2f}"
        
        # ==========================
        # 1. METRICS TABLE
        # ==========================
        print(f"\n{'='*25} SIMULATION REPORT {'='*25}")
        print(f"{'PID':<5} {'AT':<8} {'BT':<8} {'CT':<8} {'TAT':<8} {'WT':<8} {'RT':<8}")
        print("-" * 65)

        sum_tat, sum_wt, sum_rt = 0, 0, 0
        sorted_processes = sorted(self.processes, key=lambda p: p.pid)
        n = len(sorted_processes)

        for p in sorted_processes:
            # Scale internal ticks back to user time units
            at = p.arrival_time / TIME_SCALE
            bt = p.burst_time / TIME_SCALE
            ct = p.completion_time / TIME_SCALE
            
            tat = p.turnaround_time / TIME_SCALE
            wt = p.wait_time / TIME_SCALE
            rt = p.response_time / TIME_SCALE

            
            sum_tat += tat
            sum_wt += wt
            sum_rt += rt

            print(f"{p.pid:<5} {fmt(at):<8} {fmt(bt):<8} {fmt(ct):<8} {fmt(tat):<8} {fmt(wt):<8} {fmt(rt):<8}")
            # PID AT BT CT TAT WT RT
        
        # average TAT WT RT
        average_TAT=fmt(sum_tat/n)
        average_WT=fmt(sum_wt/n)
        average_RT=fmt(sum_rt/n)
        
        if n > 0: # avoid division by zero
            # Calculate the average TAT, WT, RT
            print("-" * 65)
            print(f"AVG  : {'-':<8} {'-':<8} {'-':<8} {average_TAT:<8} {average_WT:<8} {average_RT:<8}")


        # ==========================
        # 2. SEQUENTIAL EVENT LOG (DEBUG VIEW)
        # ==========================
        print("\n\n[ Event Sequence Debugger ]")
        print("Format: EventType(Start-End)  |  '->' implies sequence order, not time gap.")
        print("-" * 80)
        
        if not self.logs:
            print("No logs available.")
            return

        # 1. Collect all events per process
        # We store tuples: (start_time, priority_order, string_label)
        # priority_order ensures Arrival (0) appears before Execution (1) if they happen at same tick.
        process_events = {p.pid: [] for p in self.processes}

        # Add Arrivals
        for p in self.processes:
            label = f"AT({fmt(p.arrival_time, True)})"
            # Priority 0: Arrivals come first
            process_events[p.pid].append((p.arrival_time, 0, label))

        # Add Simulation Logs
        for log in self.logs:
            if log.pid is None: continue # Skip idle
            if log.start_time == log.end_time: continue # Skip instantaneous system events

            start_time_str = fmt(log.start_time, True)
            end_time_str = fmt(log.end_time, True)

            if log.event_type == 'EXECUTING':
                lbl = f"Exec({start_time_str}-{end_time_str})"
            elif 'CS_LOAD' in log.event_type:
                lbl = f"Load({start_time_str}-{end_time_str})"
            elif 'CS_SAVE' in log.event_type:
                lbl = f"Save({start_time_str}-{end_time_str})"
            else:
                lbl = f"{log.event_type}({start_time_str}-{end_time_str})"
            
            # Priority 1: Regular events
            process_events[log.pid].append((log.start_time, 1, lbl))

        # 2. Sort and Print
        for pid in sorted(process_events.keys()):
            # Sort by Start Time, then Priority
            events = sorted(process_events[pid], key=lambda x: (x[0], x[1]))
            
            # Extract just the labels
            event_labels = [e[2] for e in events]
            
            # Join with arrow
            timeline_str = " -> ".join(event_labels)
            
            print(f"P{pid:<3} : {timeline_str}")
        print("\n")
        print(self.logs)
        
        # ==========================
        # 3. Blender
        # ==========================
#        BlenderCode.blackboard_reset()
        # BlenderCode.generate_gantt_and_metrics_table_blender(self.logs, self.processes, input_quantum_time, input_cs_time, input_algorithm, TIME_SCALE)
        
        

input_list: InputList = [[0, 1], [0, 8], [3, 1], [20, 11]] 
input_quantum_time: float = 1
input_cs_time: float = 4
input_algorithm: STSAlgo = "MLFQ"

## Input Validation
scheduler_mode: SchedulerMode = validate_input_and_determine_scheduler_mode(data_list=input_list, q=input_quantum_time, cs=input_cs_time)
(data_list_scaled, q_scaled, cs_scaled, TIME_SCALE) = scale_input_time(data_list=input_list, q=input_quantum_time, cs=input_cs_time, scheduler_mode=scheduler_mode, max_precision=4)


# Scheduling
scheduler = Scheduler(data_list_scaled, cs_scaled, q_scaled, scheduler_mode)
scheduler.run(input_algorithm)

