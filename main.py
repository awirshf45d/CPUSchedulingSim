from typing import Literal, Union, List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from definitions import (
    TICK, CURRENT_TIME,
    SimulationLog, SystemState, SchedulerMode, EventType,
    Process, Job, ProcessState, ProcessCategory,
    InputList, validate_input_and_determine_scheduler_mode, scale_input_time,
    QueueLevel, JobPool, STSAlgo, LTSAlgo
)

# --- Logging Data Structure ---

@dataclass
class Scheduler:
    input_data_list: InputList
    cs: int
    half_cs: float = field(init=False)
    q: int
    mode: SchedulerMode
    logs: List[SimulationLog] = field(init=False, default_factory=list)
    def __post_init__(self) -> None:
        """
        Initializes the scheduler
        """
        self.half_cs = self.cs/2
        self.input_data_list.sort(key=lambda x: x[0]) # sorted based on the at

        # self.in_switch = False
        # self.switch_phase = None  # "save" or "load"
        # self.switch_remaining = 0  # Incremented each tick during CS
        # self.outgoing_process = None  # For save phase

    def run(self) -> None:
        """
        Main driver: runs specific algorithms based on the detected SchedulerMode.
        """
        algorithms = []
        if self.mode is SchedulerMode.PROCESS:
            algorithms = ["FCFS", "SPN", "HRRN", "RR", "SRTF", "MLFQ"]
        elif self.mode is SchedulerMode.MLQ:
            algorithms = ["MLQ"]
        elif self.mode is SchedulerMode.JOB:
            algorithms = ["FIFO", "SJF", "Random"]
        
        for algo in algorithms:
            self._run_single_algorithm(algo)

        self.generate_gantt_and_metrics()
    
    def _run_single_algorithm(self, algorithm:Union[STSAlgo,LTSAlgo]):
        print(f"Running Algorithm: {algorithm}...")
        
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
        
        
        if self.mode is SchedulerMode.JOB:
            job_pool = JobPool(algo=algorithm, pool=[])
            while completed_count < total_data_items:
                
                # 1. Handle Arrivals
                while next_arrival_idx < total_data_items:
                    proc = processes[next_arrival_idx]
                    if proc.arrival_time <= current_time:
                        proc.state = ProcessState.READY
                        ready_queue.append(proc)
                        next_arrival_idx += 1
                    else:
                        break
                
                # 2. Check Preemption (Only if EXECUTING)
                # According to backbone: "If system_state == EXECUTING... check_preemption"
                if system_state == SystemState.EXECUTING and current_process:
                    if self._check_preemption(algorithm, current_process, ready_queue, current_quantum_counter):
                        # Preemption Triggered
                        self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "EXECUTING")
                        segment_start_time = current_time
                        
                        outgoing_process = current_process
                        current_process = None
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                        else:
                            # Instant Switch
                            outgoing_process.state = ProcessState.READY
                            ready_queue.append(outgoing_process)
                            outgoing_process = None
                            system_state = SystemState.IDLE
                
                # 3. Update Waiting Metrics
                # Increment wait time for everyone in ready queue
                for p in ready_queue:
                    p.wait_time += TICK
                    
                # 4. Handle State Machine
                
                if system_state == SystemState.CS_LOAD:
                    cs_progress += TICK
                    
                    # Check Abort (Preemption during Load)
                    # Backbone: "If algo allows aborts and check_preemption... Log aborted... Return incoming to queue"
                    # Note: 'current_process' here is the one *being loaded*.
                    if self._is_preemptive(algorithm) and current_process:
                        # We check if there is a BETTER process than the one we are loading
                        # Note: We must temporarily put current_process in queue to compare, or compare directly
                        best_candidate = self._peek_next_process(algorithm, ready_queue, current_time)
                        
                        should_abort = False
                        if best_candidate and algorithm == "SRTF":
                            if best_candidate.remaining_time < current_process.remaining_time:
                                should_abort = True
                        elif best_candidate and algorithm == "RR":
                            pass # RR usually doesn't abort CS for arrival, only quantum expiry
                            
                        if should_abort:
                            self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "CS_ABORT")
                            segment_start_time = current_time
                            
                            # Return 'incoming' to queue
                            current_process.state = ProcessState.READY
                            ready_queue.append(current_process)
                            current_process = None
                            
                            system_state = SystemState.IDLE
                            cs_progress = 0
                            continue # Skip to next tick

                    if cs_progress >= self.half_cs_scaled:
                        # Load Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "CS_LOAD")
                        segment_start_time = current_time + TICK
                        
                        system_state = SystemState.EXECUTING
                        current_process.state = ProcessState.RUNNING
                        current_quantum_counter = 0
                        
                        # First run metrics
                        if current_process.start_time == -1:
                            current_process.start_time = current_time + TICK
                            current_process.response_time = current_process.start_time - current_process.arrival_time
                            
                elif system_state == SystemState.CS_SAVE:
                    cs_progress += TICK
                    
                    # Check Abort (Preemption during Save)
                    # Backbone: "If algo allows aborts and check_preemption on outgoing... Resume outgoing"
                    # This implies: If the reason we preempted (e.g. a short job arrived) is no longer valid?
                    # Or if the outgoing process becomes the best choice again?
                    # This is rare in standard algos but possible in complex priority shifts.
                    # We skip complex save-abort for standard algorithms to keep it stable, unless explicitly needed.
                    
                    if cs_progress >= self.half_cs_scaled:
                        # Save Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, outgoing_process.pid, "CS_SAVE")
                        segment_start_time = current_time + TICK
                        
                        # Logic: If outgoing has remaining > 0, back to ready. Else Terminated.
                        if outgoing_process.remaining_time > 0:
                            outgoing_process.state = ProcessState.READY
                            ready_queue.append(outgoing_process)
                        else:
                            outgoing_process.state = ProcessState.TERMINATED
                            # Completion metrics handled when it hit 0 remaining time
                        
                        outgoing_process = None
                        system_state = SystemState.CS_LOAD
                        cs_progress = 0
                        
                elif system_state == SystemState.EXECUTING:
                    current_process.remaining_time -= TICK
                    current_quantum_counter += TICK
                    
                    if current_process.remaining_time <= 0:
                        # Burst Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "EXECUTING")
                        segment_start_time = current_time + TICK
                        
                        current_process.completion_time = current_time + TICK
                        current_process.turnaround_time = current_process.completion_time - current_process.arrival_time
                        # Wait time is calculated incrementally in step 3, but formula is safer:
                        # wt = tat - burst. We can reconcile later.
                        
                        current_process.state = ProcessState.TERMINATED
                        completed_count += 1
                        
                        outgoing_process = current_process
                        current_process = None
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                        else:
                            system_state = SystemState.IDLE
                            
                elif system_state == SystemState.IDLE:
                    # Try to pick next process
                    candidate = self._select_next_process(algorithm, ready_queue, current_time)
                    
                    if candidate:
                        # Log IDLE time if we were waiting
                        if current_time > segment_start_time:
                            self._add_log(algorithm, segment_start_time, current_time, None, "IDLE")
                            segment_start_time = current_time
                        
                        current_process = candidate # Removed from queue by _select_next_process
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_LOAD
                            cs_progress = 0
                        else:
                            system_state = SystemState.EXECUTING
                            current_process.state = ProcessState.RUNNING
                            current_quantum_counter = 0
                            if current_process.start_time == -1:
                                current_process.start_time = current_time
                                current_process.response_time = current_process.start_time - current_process.arrival_time
                
                # 5. Advance Time
                current_time += TICK
                
                # 6. Safety Break
                if system_state is SystemState.IDLE and not ready_queue and next_arrival_idx == total_data_items and current_process is None:
                    # End of simulation
                    break
                    
            # Close final log
            if segment_start_time < current_time:
                pass # Optional: log final idle or state
        elif self.mode is SchedulerMode.PROCESS:            
            ready_queue: List[QueueLevel] = [
                QueueLevel(
                    q=self.q if algorithm in ["RR", "SRTF", "MLFQ"] else None, # Preemptive logic
                    algo=algorithm
                )
            ] # len(ready_queue) must be equal to 1, edit: for MLFQ at first this value is 0 as well.
            while completed_count < total_data_items:
                
                # 1. Handle Arrivals.
                while next_arrival_idx < total_data_items:
                    proc = self.processes[next_arrival_idx]
                    if proc.arrival_time <= current_time:
                        proc.state = ProcessState.READY
                        # add to ready queue
                        ready_queue[0].queue.append(proc)
                        ready_queue[0].new_event_occurred = True
                        proc.process_ready_queue_id = 0
                        next_arrival_idx += 1
                        # log
                        self._add_log(algorithm, CURRENT_TIME, proc.pid, EventType.PROCESS_ARRIVAL.value)
                    else:
                        break
                
                # 2. Check Preemption (Only if an event occurred), only if system executing
                if (
                    (current_process and system_state is SystemState.EXECUTING) # quantum time expired? 
                    or any(sub_queue.new_event_occurred for sub_queue in ready_queue) # higher priority process arrived?
                ):
                    if self._check_preemption(current_process, ready_queue, current_quantum_counter, system_state):
                        # Preemption Triggered
                        self._add_log(algorithm, CURRENT_TIME, current_process.pid, "EXECUTING")
                        segment_start_time = current_time
                        
                        outgoing_process = current_process
                        current_process = None
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                        else:
                            # Instant Switch
                            outgoing_process.state = ProcessState.READY
                            ready_queue.append(outgoing_process)
                            outgoing_process = None
                            system_state = SystemState.IDLE
                    
                    for sub_queue in ready_queue:
                        sub_queue.new_event_occurred = False
                    
                
                # 3. Update Waiting Metrics
                # Increment wait time for everyone in ready queue
                for p in ready_queue:
                    p.wait_time += TICK
                    
                # 4. Handle State Machine
                
                if system_state == SystemState.CS_LOAD:
                    cs_progress += TICK
                    
                    # Check Abort (Preemption during Load)
                    # Backbone: "If algo allows aborts and check_preemption... Log aborted... Return incoming to queue"
                    # Note: 'current_process' here is the one *being loaded*.
                    if self._is_preemptive(algorithm) and current_process:
                        # We check if there is a BETTER process than the one we are loading
                        # Note: We must temporarily put current_process in queue to compare, or compare directly
                        best_candidate = self._peek_next_process(algorithm, ready_queue, current_time)
                        
                        should_abort = False
                        if best_candidate and algorithm == "SRTF":
                            if best_candidate.remaining_time < current_process.remaining_time:
                                should_abort = True
                        elif best_candidate and algorithm == "RR":
                            pass # RR usually doesn't abort CS for arrival, only quantum expiry
                            
                        if should_abort:
                            self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "CS_ABORT")
                            segment_start_time = current_time
                            
                            # Return 'incoming' to queue
                            current_process.state = ProcessState.READY
                            ready_queue.append(current_process)
                            current_process = None
                            
                            system_state = SystemState.IDLE
                            cs_progress = 0
                            continue # Skip to next tick

                    if cs_progress >= self.half_cs_scaled:
                        # Load Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "CS_LOAD")
                        segment_start_time = current_time + TICK
                        
                        system_state = SystemState.EXECUTING
                        current_process.state = ProcessState.RUNNING
                        current_quantum_counter = 0
                        
                        # First run metrics
                        if current_process.start_time == -1:
                            current_process.start_time = current_time + TICK
                            current_process.response_time = current_process.start_time - current_process.arrival_time
                            
                elif system_state == SystemState.CS_SAVE:
                    cs_progress += TICK
                    
                    # Check Abort (Preemption during Save)
                    # Backbone: "If algo allows aborts and check_preemption on outgoing... Resume outgoing"
                    # This implies: If the reason we preempted (e.g. a short job arrived) is no longer valid?
                    # Or if the outgoing process becomes the best choice again?
                    # This is rare in standard algos but possible in complex priority shifts.
                    # We skip complex save-abort for standard algorithms to keep it stable, unless explicitly needed.
                    
                    if cs_progress >= self.half_cs_scaled:
                        # Save Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, outgoing_process.pid, "CS_SAVE")
                        segment_start_time = current_time + TICK
                        
                        # Logic: If outgoing has remaining > 0, back to ready. Else Terminated.
                        if outgoing_process.remaining_time > 0:
                            outgoing_process.state = ProcessState.READY
                            ready_queue.append(outgoing_process)
                        else:
                            outgoing_process.state = ProcessState.TERMINATED
                            # Completion metrics handled when it hit 0 remaining time
                        
                        outgoing_process = None
                        system_state = SystemState.CS_LOAD
                        cs_progress = 0
                        
                elif system_state == SystemState.EXECUTING:
                    current_process.remaining_time -= TICK
                    current_quantum_counter += TICK
                    
                    if current_process.remaining_time <= 0:
                        # Burst Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "EXECUTING")
                        segment_start_time = current_time + TICK
                        
                        current_process.completion_time = current_time + TICK
                        current_process.turnaround_time = current_process.completion_time - current_process.arrival_time
                        # Wait time is calculated incrementally in step 3, but formula is safer:
                        # wt = tat - burst. We can reconcile later.
                        
                        current_process.state = ProcessState.TERMINATED
                        completed_count += 1
                        
                        outgoing_process = current_process
                        current_process = None
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                        else:
                            system_state = SystemState.IDLE
                            
                elif system_state == SystemState.IDLE:
                    # Try to pick next process
                    candidate = self._select_next_process(algorithm, ready_queue, current_time)
                    
                    if candidate:
                        # Log IDLE time if we were waiting
                        if current_time > segment_start_time:
                            self._add_log(algorithm, segment_start_time, current_time, None, "IDLE")
                            segment_start_time = current_time
                        
                        current_process = candidate # Removed from queue by _select_next_process
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_LOAD
                            cs_progress = 0
                        else:
                            system_state = SystemState.EXECUTING
                            current_process.state = ProcessState.RUNNING
                            current_quantum_counter = 0
                            if current_process.start_time == -1:
                                current_process.start_time = current_time
                                current_process.response_time = current_process.start_time - current_process.arrival_time
                
                # 5. Advance Time
                current_time += TICK
                
                # 6. Safety Break
                if system_state is SystemState.IDLE and not ready_queue and next_arrival_idx == total_data_items and current_process is None:
                    # End of simulation
                    break
                    
            # Close final log
            if segment_start_time < current_time:
                pass # Optional: log final idle or state
        else: # MLQ
            # For MLQ we would map categories to queues.
            multilevel_ready_queue: List[QueueLevel] = [
                QueueLevel(category=ProcessCategory.REAL_TIME, q=self.q, algo="RR", queue=[]),
                QueueLevel(category=ProcessCategory.SYSTEM, q=self.q, algo="SRTF", queue=[]),
                QueueLevel(category=ProcessCategory.INTERACTIVE, q=self.q, algo="RR", queue=[]),
                QueueLevel(category=ProcessCategory.BATCH, q=None, algo="FCFS", queue=[])
            ]
            while completed_count < total_data_items:
            
                # 1. Handle Arrivals
                while next_arrival_idx < total_data_items:
                    proc = processes[next_arrival_idx]
                    if proc.arrival_time <= current_time:
                        proc.state = ProcessState.READY
                        ready_queue.append(proc)
                        next_arrival_idx += 1
                    else:
                        break
                
                # 2. Check Preemption (Only if EXECUTING)
                # According to backbone: "If system_state == EXECUTING... check_preemption"
                if system_state == SystemState.EXECUTING and current_process:
                    if self._check_preemption(algorithm, current_process, ready_queue, current_quantum_counter):
                        # Preemption Triggered
                        self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "EXECUTING")
                        segment_start_time = current_time
                        
                        outgoing_process = current_process
                        current_process = None
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                        else:
                            # Instant Switch
                            outgoing_process.state = ProcessState.READY
                            ready_queue.append(outgoing_process)
                            outgoing_process = None
                            system_state = SystemState.IDLE
                
                # 3. Update Waiting Metrics
                # Increment wait time for everyone in ready queue
                for p in ready_queue:
                    p.wait_time += TICK
                    
                # 4. Handle State Machine
                
                if system_state == SystemState.CS_LOAD:
                    cs_progress += TICK
                    
                    # Check Abort (Preemption during Load)
                    # Backbone: "If algo allows aborts and check_preemption... Log aborted... Return incoming to queue"
                    # Note: 'current_process' here is the one *being loaded*.
                    if self._is_preemptive(algorithm) and current_process:
                        # We check if there is a BETTER process than the one we are loading
                        # Note: We must temporarily put current_process in queue to compare, or compare directly
                        best_candidate = self._peek_next_process(algorithm, ready_queue, current_time)
                        
                        should_abort = False
                        if best_candidate and algorithm == "SRTF":
                            if best_candidate.remaining_time < current_process.remaining_time:
                                should_abort = True
                        elif best_candidate and algorithm == "RR":
                            pass # RR usually doesn't abort CS for arrival, only quantum expiry
                            
                        if should_abort:
                            self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "CS_ABORT")
                            segment_start_time = current_time
                            
                            # Return 'incoming' to queue
                            current_process.state = ProcessState.READY
                            ready_queue.append(current_process)
                            current_process = None
                            
                            system_state = SystemState.IDLE
                            cs_progress = 0
                            continue # Skip to next tick

                    if cs_progress >= self.half_cs_scaled:
                        # Load Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "CS_LOAD")
                        segment_start_time = current_time + TICK
                        
                        system_state = SystemState.EXECUTING
                        current_process.state = ProcessState.RUNNING
                        current_quantum_counter = 0
                        
                        # First run metrics
                        if current_process.start_time == -1:
                            current_process.start_time = current_time + TICK
                            current_process.response_time = current_process.start_time - current_process.arrival_time
                            
                elif system_state == SystemState.CS_SAVE:
                    cs_progress += TICK
                    
                    # Check Abort (Preemption during Save)
                    # Backbone: "If algo allows aborts and check_preemption on outgoing... Resume outgoing"
                    # This implies: If the reason we preempted (e.g. a short job arrived) is no longer valid?
                    # Or if the outgoing process becomes the best choice again?
                    # This is rare in standard algos but possible in complex priority shifts.
                    # We skip complex save-abort for standard algorithms to keep it stable, unless explicitly needed.
                    
                    if cs_progress >= self.half_cs_scaled:
                        # Save Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, outgoing_process.pid, "CS_SAVE")
                        segment_start_time = current_time + TICK
                        
                        # Logic: If outgoing has remaining > 0, back to ready. Else Terminated.
                        if outgoing_process.remaining_time > 0:
                            outgoing_process.state = ProcessState.READY
                            ready_queue.append(outgoing_process)
                        else:
                            outgoing_process.state = ProcessState.TERMINATED
                            # Completion metrics handled when it hit 0 remaining time
                        
                        outgoing_process = None
                        system_state = SystemState.CS_LOAD
                        cs_progress = 0
                        
                elif system_state == SystemState.EXECUTING:
                    current_process.remaining_time -= TICK
                    current_quantum_counter += TICK
                    
                    if current_process.remaining_time <= 0:
                        # Burst Complete
                        self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "EXECUTING")
                        segment_start_time = current_time + TICK
                        
                        current_process.completion_time = current_time + TICK
                        current_process.turnaround_time = current_process.completion_time - current_process.arrival_time
                        # Wait time is calculated incrementally in step 3, but formula is safer:
                        # wt = tat - burst. We can reconcile later.
                        
                        current_process.state = ProcessState.TERMINATED
                        completed_count += 1
                        
                        outgoing_process = current_process
                        current_process = None
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_SAVE
                            cs_progress = 0
                        else:
                            system_state = SystemState.IDLE
                            
                elif system_state == SystemState.IDLE:
                    # Try to pick next process
                    candidate = self._select_next_process(algorithm, ready_queue, current_time)
                    
                    if candidate:
                        # Log IDLE time if we were waiting
                        if current_time > segment_start_time:
                            self._add_log(algorithm, segment_start_time, current_time, None, "IDLE")
                            segment_start_time = current_time
                        
                        current_process = candidate # Removed from queue by _select_next_process
                        
                        if self.cs_scaled > 0:
                            system_state = SystemState.CS_LOAD
                            cs_progress = 0
                        else:
                            system_state = SystemState.EXECUTING
                            current_process.state = ProcessState.RUNNING
                            current_quantum_counter = 0
                            if current_process.start_time == -1:
                                current_process.start_time = current_time
                                current_process.response_time = current_process.start_time - current_process.arrival_time
                
                # 5. Advance Time
                current_time += TICK
                
                # 6. Safety Break
                if system_state is SystemState.IDLE and not ready_queue and next_arrival_idx == total_data_items and current_process is None:
                    # End of simulation
                    break
                    
            # Close final log
            if segment_start_time < current_time:
                pass # Optional: log final idle or state
        
        # while completed_count < total_data_items:
            
        #     # 1. Handle Arrivals
        #     while next_arrival_idx < total_data_items:
        #         proc = processes[next_arrival_idx]
        #         if proc.arrival_time <= current_time:
        #             proc.state = ProcessState.READY
        #             ready_queue.append(proc)
        #             next_arrival_idx += 1
        #         else:
        #             break
            
        #     # 2. Check Preemption (Only if EXECUTING)
        #     # According to backbone: "If system_state == EXECUTING... check_preemption"
        #     if system_state == SystemState.EXECUTING and current_process:
        #         if self._check_preemption(algorithm, current_process, ready_queue, current_quantum_counter):
        #             # Preemption Triggered
        #             self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "EXECUTING")
        #             segment_start_time = current_time
                    
        #             outgoing_process = current_process
        #             current_process = None
                    
        #             if self.cs_scaled > 0:
        #                 system_state = SystemState.CS_SAVE
        #                 cs_progress = 0
        #             else:
        #                 # Instant Switch
        #                 outgoing_process.state = ProcessState.READY
        #                 ready_queue.append(outgoing_process)
        #                 outgoing_process = None
        #                 system_state = SystemState.IDLE
            
        #     # 3. Update Waiting Metrics
        #     # Increment wait time for everyone in ready queue
        #     for p in ready_queue:
        #         p.wait_time += TICK
                
        #     # 4. Handle State Machine
            
        #     if system_state == SystemState.CS_LOAD:
        #         cs_progress += TICK
                
        #         # Check Abort (Preemption during Load)
        #         # Backbone: "If algo allows aborts and check_preemption... Log aborted... Return incoming to queue"
        #         # Note: 'current_process' here is the one *being loaded*.
        #         if self._is_preemptive(algorithm) and current_process:
        #             # We check if there is a BETTER process than the one we are loading
        #             # Note: We must temporarily put current_process in queue to compare, or compare directly
        #             best_candidate = self._peek_next_process(algorithm, ready_queue, current_time)
                    
        #             should_abort = False
        #             if best_candidate and algorithm == "SRTF":
        #                 if best_candidate.remaining_time < current_process.remaining_time:
        #                     should_abort = True
        #             elif best_candidate and algorithm == "RR":
        #                 pass # RR usually doesn't abort CS for arrival, only quantum expiry
                        
        #             if should_abort:
        #                 self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "CS_ABORT")
        #                 segment_start_time = current_time
                        
        #                 # Return 'incoming' to queue
        #                 current_process.state = ProcessState.READY
        #                 ready_queue.append(current_process)
        #                 current_process = None
                        
        #                 system_state = SystemState.IDLE
        #                 cs_progress = 0
        #                 continue # Skip to next tick

        #         if cs_progress >= self.half_cs_scaled:
        #             # Load Complete
        #             self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "CS_LOAD")
        #             segment_start_time = current_time + TICK
                    
        #             system_state = SystemState.EXECUTING
        #             current_process.state = ProcessState.RUNNING
        #             current_quantum_counter = 0
                    
        #             # First run metrics
        #             if current_process.start_time == -1:
        #                 current_process.start_time = current_time + TICK
        #                 current_process.response_time = current_process.start_time - current_process.arrival_time
                        
        #     elif system_state == SystemState.CS_SAVE:
        #         cs_progress += TICK
                
        #         # Check Abort (Preemption during Save)
        #         # Backbone: "If algo allows aborts and check_preemption on outgoing... Resume outgoing"
        #         # This implies: If the reason we preempted (e.g. a short job arrived) is no longer valid?
        #         # Or if the outgoing process becomes the best choice again?
        #         # This is rare in standard algos but possible in complex priority shifts.
        #         # We skip complex save-abort for standard algorithms to keep it stable, unless explicitly needed.
                
        #         if cs_progress >= self.half_cs_scaled:
        #             # Save Complete
        #             self._add_log(algorithm, segment_start_time, current_time + TICK, outgoing_process.pid, "CS_SAVE")
        #             segment_start_time = current_time + TICK
                    
        #             # Logic: If outgoing has remaining > 0, back to ready. Else Terminated.
        #             if outgoing_process.remaining_time > 0:
        #                 outgoing_process.state = ProcessState.READY
        #                 ready_queue.append(outgoing_process)
        #             else:
        #                 outgoing_process.state = ProcessState.TERMINATED
        #                 # Completion metrics handled when it hit 0 remaining time
                    
        #             outgoing_process = None
        #             system_state = SystemState.CS_LOAD
        #             cs_progress = 0
                    
        #     elif system_state == SystemState.EXECUTING:
        #         current_process.remaining_time -= TICK
        #         current_quantum_counter += TICK
                
        #         if current_process.remaining_time <= 0:
        #             # Burst Complete
        #             self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "EXECUTING")
        #             segment_start_time = current_time + TICK
                    
        #             current_process.completion_time = current_time + TICK
        #             current_process.turnaround_time = current_process.completion_time - current_process.arrival_time
        #             # Wait time is calculated incrementally in step 3, but formula is safer:
        #             # wt = tat - burst. We can reconcile later.
                    
        #             current_process.state = ProcessState.TERMINATED
        #             completed_count += 1
                    
        #             outgoing_process = current_process
        #             current_process = None
                    
        #             if self.cs_scaled > 0:
        #                 system_state = SystemState.CS_SAVE
        #                 cs_progress = 0
        #             else:
        #                 system_state = SystemState.IDLE
                        
        #     elif system_state == SystemState.IDLE:
        #         # Try to pick next process
        #         candidate = self._select_next_process(algorithm, ready_queue, current_time)
                
        #         if candidate:
        #             # Log IDLE time if we were waiting
        #             if current_time > segment_start_time:
        #                 self._add_log(algorithm, segment_start_time, current_time, None, "IDLE")
        #                 segment_start_time = current_time
                    
        #             current_process = candidate # Removed from queue by _select_next_process
                    
        #             if self.cs_scaled > 0:
        #                 system_state = SystemState.CS_LOAD
        #                 cs_progress = 0
        #             else:
        #                 system_state = SystemState.EXECUTING
        #                 current_process.state = ProcessState.RUNNING
        #                 current_quantum_counter = 0
        #                 if current_process.start_time == -1:
        #                     current_process.start_time = current_time
        #                     current_process.response_time = current_process.start_time - current_process.arrival_time
            
        #     # 5. Advance Time
        #     current_time += TICK
            
        #     # 6. Safety Break
        #     if system_state is SystemState.IDLE and not ready_queue and next_arrival_idx == total_data_items and current_process is None:
        #         # End of simulation
        #         break
                
        # # Close final log
        # if segment_start_time < current_time:
        #      pass # Optional: log final idle or state

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
        CURRENT_TIME = 0


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

    def _peek_next_process(self, algo: str, ready_queue: List[Process], current_time: int) -> Optional[Process]:
        """ Inspects next process without removing it. """
        if not ready_queue:
            return None
        
        # Sort/Find based on algo
        if algo in ["FCFS", "RR"]:
            return ready_queue[0]
        elif algo in ["SJF", "SRTF"]:
            # Tie breaker: Arrival time
            return min(ready_queue, key=lambda p: (p.remaining_time, p.arrival_time))
        elif algo == "HRRN":
            return self._get_hrrn_candidate(ready_queue, current_time)
        return ready_queue[0]

    def _select_next_process(self, algo: str, ready_queue: List[Process], current_time: int) -> Optional[Process]:
        """ Selects and REMOVES next process from queue. """
        candidate = self._peek_next_process(algo, ready_queue, current_time)
        if candidate:
            ready_queue.remove(candidate)
        return candidate

    def _get_hrrn_candidate(self, ready_queue: List[Process], current_time: int) -> Process:
        # R = (w + s) / s
        best = None
        max_ratio = -1.0
        for p in ready_queue:
            wait = current_time - p.arrival_time - (p.burst_time - p.remaining_time)
            # Avoid div by zero if burst is 0 (shouldn't happen)
            ratio = (wait + p.burst_time) / p.burst_time if p.burst_time > 0 else 0
            if ratio > max_ratio:
                max_ratio = ratio
                best = p
        return best

    def _add_log(self, algo: str, time: float, id: Optional[int], event_type: EventType):
        self.logs.append(SimulationLog(algo, time, id, event_type))

    def generate_gantt_and_metrics(self):
        """
        Generates terminal-based Gantt chart and Metrics table.
        """
        # Get unique algorithms run
        algos = sorted(list(set(l.algorithm for l in self.logs)))
        
        for algo in algos:
            algo_logs = [l for l in self.logs if l.algorithm == algo]
            print(f"\n{'='*25} {algo} REPORT {'='*25}")
            
            # --- Metrics ---
            # Reconstruct metrics from logs to ensure they match what happened
            pids = set(l.pid for l in algo_logs if l.pid is not None)
            metrics = {pid: {'at': 0, 'bt': 0, 'ct': 0, 'start': -1} for pid in pids}
            
            # Fill AT/BT from inputs
            for pid in pids:
                # Assuming raw inputs align with PIDs 0..N
                if self.mode == SchedulerMode.PROCESS:
                    metrics[pid]['at'] = self.input_data[pid][0]
                    metrics[pid]['bt'] = self.input_data[pid][1]
                else:
                    metrics[pid]['at'] = self.input_data[pid][0]
                    metrics[pid]['bt'] = self.input_data[pid][1]

            # Parse logs for Start/End times
            for log in algo_logs:
                if log.pid is not None:
                    # Start Time: First time we see EXECUTING
                    if log.system_state == "EXECUTING" or log.system_state == "CS_LOAD":
                         # CS_LOAD implies preparation, EXECUTING implies running.
                         # Response time is usually measured from Arrival to First Execution.
                         if log.system_state == "EXECUTING" and metrics[log.pid]['start'] == -1:
                             metrics[log.pid]['start'] = log.start_time / self.time_scale_factor
                    
                    # Completion Time: The end of the last EXECUTE/CS_SAVE block?
                    # Safer: logic in run loop set CT. Here we infer max end time.
                    if log.system_state == "EXECUTING":
                        t_end = log.end_time / self.time_scale_factor
                        if t_end > metrics[log.pid]['ct']:
                            metrics[log.pid]['ct'] = t_end

            # Calculate Derived Metrics
            total_tat, total_wt, total_rt = 0, 0, 0
            count = len(pids)
            
            print(f"{'PID':<5} {'AT':<8} {'BT':<8} {'CT':<8} {'TAT':<8} {'WT':<8} {'RT':<8}")
            print("-" * 65)
            
            for pid in sorted(pids):
                m = metrics[pid]
                ct = m['ct']
                at = m['at']
                bt = m['bt']
                start = m['start'] if m['start'] != -1 else at # Fallback
                
                tat = ct - at
                wt = tat - bt
                rt = start - at
                
                total_tat += tat; total_wt += wt; total_rt += rt
                
                print(f"{pid:<5} {at:<8.2f} {bt:<8.2f} {ct:<8.2f} {tat:<8.2f} {wt:<8.2f} {rt:<8.2f}")
            
            if count > 0:
                print("-" * 65)
                print(f"AVG  : {'-':<8} {'-':<8} {'-':<8} {total_tat/count:<8.2f} {total_wt/count:<8.2f} {total_rt/count:<8.2f}")

            # --- Gantt Chart ---
            print("\n[Gantt Chart Flow]")
            for log in algo_logs:
                s = log.start_time / self.time_scale_factor
                e = log.end_time / self.time_scale_factor
                dur = e - s
                if dur <= 0: continue
                
                lbl = log.system_state
                if log.pid is not None: lbl += f"(P{log.pid})"
                
                # Simple text bar
                bar = "█" * int(min(20, dur * 2)) 
                print(f"{s:6.2f} -> {e:6.2f} : {lbl:<15} {bar}")



# Input Section
input_list: InputList = [ [1, 6], [80000, 50000], [102500, 20000], [175000, 30000] ] # at, cbt / at, cbt, category / at, cbt, m
input_quantum_time: float = 3
input_cs_time: float = 1

## Input Validation
scheduler_mode: SchedulerMode = validate_input_and_determine_scheduler_mode(data_list=input_list, q=input_quantum_time, cs=input_cs_time)
(data_list_scaled, q_scaled, cs_scaled) = scale_input_time(data_list=input_list, q=input_quantum_time, cs=input_cs_time, scheduler_mode=scheduler_mode, max_precision=4)


# Scheduling
scheduler = Scheduler(data_list_scaled, cs_scaled, q_scaled, scheduler_mode)
scheduler.run()

# Visualization