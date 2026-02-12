def _run_single_algorithm(self, algorithm:Union[STSAlgo,LTSAlgo]):
    # print(f"Running Algorithm: {algorithm}...")
    
    # # --- Initialization ---
    # self._reset_simulation_objects()
    # system_state = SystemState.IDLE
    # current_process: Optional[Process] = None
    # outgoing_process: Optional[Process] = None # For CS_SAVE
    # # CS Tracking
    # cs_progress = 0
    # # Quantum Tracking
    # current_quantum_counter = 0
    # # Logging Pointers
    # segment_start_time = 0
    # next_arrival_idx = 0
    # completed_count = 0
    # total_data_items = len(self.input_data_list)
    
    
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