import math
from typing import List, Dict, Optional, Tuple, Deque
from dataclasses import dataclass, field
from collections import deque

# Import from your provided definitions.py
from definitionss import (
    TICK,
    Process, ProcessState, ProcessCategory,
    InputList, SchedulerMode,
    validate_input_and_determine_scheduler_mode, scale_input_time,
    CPUState
)

# --- Logging Data Structure ---
@dataclass
class SimulationLog:
    algorithm: str
    start_time: int
    end_time: int
    pid: Optional[int]
    system_state: str  # IDLE, CS_LOAD, CS_SAVE, EXECUTING, CS_ABORT
    info: str = ""

@dataclass
class CPUScheduler:
    input_data: InputList
    q: float  # Quantum time (raw ms)
    cs: float # Context Switch time (raw ms)
    
    # Internal State
    scaled_data: List[Tuple] = field(init=False)
    q_scaled: int = field(init=False)
    cs_scaled: int = field(init=False)
    half_cs_scaled: int = field(init=False)
    mode: SchedulerMode = field(init=False)
    time_scale_factor: int = field(init=False) # Estimated for reporting
    
    logs: List[SimulationLog] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """
        Initializes the scheduler by determining the mode and scaling all inputs
        to integer ticks for precise simulation.
        """
        # 1. Determine Mode
        self.mode = validate_input_and_determine_scheduler_mode(
            self.input_data, self.q, self.cs
        )
        
        # 2. Scale Time Inputs
        # scale_input_time returns (scaled_list, scaled_q, scaled_cs)
        scaled_res = scale_input_time(self.input_data, self.q, self.cs, self.mode)
        self.scaled_data = scaled_res[0]
        self.q_scaled = scaled_res[1]
        self.cs_scaled = scaled_res[2]
        self.half_cs_scaled = self.cs_scaled // 2
        
        # Estimate time scale factor for un-scaling in reports
        # If q provided, q_scaled / q is the factor. Else infer from arrival 1 vs 1*scale
        if self.q > 0:
            self.time_scale_factor = int(self.q_scaled / self.q)
        else:
            self.time_scale_factor = 10000 # Default fallback if q=0
            
    def run(self) -> None:
        """
        Main driver: runs specific algorithms based on the detected SchedulerMode.
        """
        print(f"--- Launching Scheduler [Mode: {self.mode.name}] ---")
        
        algorithms = []
        if self.mode == SchedulerMode.PROCESS:
            algorithms = ["FCFS", "SJF", "RR", "SRTF", "HRRN"]
        elif self.mode == SchedulerMode.MLQ:
            algorithms = ["MLQ"]
        elif self.mode == SchedulerMode.JOB:
            algorithms = ["FCFS_JOB"]

        for algo in algorithms:
            self._run_single_algorithm(algo)
            
        self.generate_gantt_and_metrics()

    def _reset_simulation_objects(self) -> Tuple[List[Process], int]:
        """Recreates process objects for a fresh run."""
        procs = []
        for item in self.scaled_data:
            # item structure depends on mode: 
            # PROCESS: [at, bt]
            # MLQ: [at, bt, cat]
            # JOB: [at, bt, mem]
            
            p_kwargs = {
                'pid': len(procs),
                'arrival_time': item[0],
                'burst_time': item[1]
            }
            
            if self.mode == SchedulerMode.MLQ:
                p_kwargs['category'] = item[2]
            elif self.mode == SchedulerMode.JOB:
                # Job specific attributes if needed, storing in generic Process for now
                pass 
                
            p = Process(**p_kwargs)
            procs.append(p)
        return procs, 0

    def _run_single_algorithm(self, algorithm: str):
        print(f"Running Algorithm: {algorithm}...")
        
        # --- Initialization ---
        processes, current_time = self._reset_simulation_objects()
        processes.sort(key=lambda x: x.arrival_time)
        total_processes = len(processes)
        
        # Queues
        # For MLQ we would map categories to queues. For standard, we use one 'ready_queue'.
        ready_queue: List[Process] = [] 
        
        # State Pointers
        system_state = CPUState.IDLE
        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None # For CS_SAVE
        
        # CS Tracking
        cs_progress = 0
        
        # RR Quantum Tracking
        current_quantum_counter = 0
        
        # Logging Pointers
        segment_start_time = 0
        next_arrival_idx = 0
        completed_count = 0
        
        while completed_count < total_processes:
            
            # 1. Handle Arrivals
            while next_arrival_idx < total_processes:
                proc = processes[next_arrival_idx]
                if proc.arrival_time <= current_time:
                    proc.state = ProcessState.READY
                    ready_queue.append(proc)
                    next_arrival_idx += 1
                else:
                    break
            
            # 2. Check Preemption (Only if EXECUTING)
            # According to backbone: "If system_state == EXECUTING... check_preemption"
            if system_state == CPUState.EXECUTING and current_process:
                if self._check_preemption(algorithm, current_process, ready_queue, current_quantum_counter):
                    # Preemption Triggered
                    self._add_log(algorithm, segment_start_time, current_time, current_process.pid, "EXECUTING")
                    segment_start_time = current_time
                    
                    outgoing_process = current_process
                    current_process = None
                    
                    if self.cs_scaled > 0:
                        system_state = CPUState.CS_SAVE
                        cs_progress = 0
                    else:
                        # Instant Switch
                        outgoing_process.state = ProcessState.READY
                        ready_queue.append(outgoing_process)
                        outgoing_process = None
                        system_state = CPUState.IDLE
            
            # 3. Update Waiting Metrics
            # Increment wait time for everyone in ready queue
            for p in ready_queue:
                p.wait_time += TICK
                
            # 4. Handle State Machine
            
            if system_state == CPUState.CS_LOAD:
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
                        
                        system_state = CPUState.IDLE
                        cs_progress = 0
                        continue # Skip to next tick

                if cs_progress >= self.half_cs_scaled:
                    print(f"this is meeeee")
                    print(current_process)
                    if current_process is None:
                        continue
                    # Load Complete
                    self._add_log(algorithm, segment_start_time, current_time + TICK, current_process.pid, "CS_LOAD")
                    segment_start_time = current_time + TICK
                    
                    system_state = CPUState.EXECUTING
                    current_process.state = ProcessState.RUNNING
                    current_quantum_counter = 0
                    
                    # First run metrics
                    if current_process.start_time == -1:
                        current_process.start_time = current_time + TICK
                        current_process.response_time = current_process.start_time - current_process.arrival_time
                        
            elif system_state == CPUState.CS_SAVE:
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
                    system_state = CPUState.CS_LOAD
                    cs_progress = 0
                    
            elif system_state == CPUState.EXECUTING:
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
                        system_state = CPUState.CS_SAVE
                        cs_progress = 0
                    else:
                        system_state = CPUState.IDLE
                        
            elif system_state == CPUState.IDLE:
                # Try to pick next process
                candidate = self._select_next_process(algorithm, ready_queue, current_time)
                
                if candidate:
                    # Log IDLE time if we were waiting
                    if current_time > segment_start_time:
                        self._add_log(algorithm, segment_start_time, current_time, None, "IDLE")
                        segment_start_time = current_time
                    
                    current_process = candidate # Removed from queue by _select_next_process
                    
                    if self.cs_scaled > 0:
                        system_state = CPUState.CS_LOAD
                        cs_progress = 0
                    else:
                        system_state = CPUState.EXECUTING
                        current_process.state = ProcessState.RUNNING
                        current_quantum_counter = 0
                        if current_process.start_time == -1:
                            current_process.start_time = current_time
                            current_process.response_time = current_process.start_time - current_process.arrival_time
            
            # 5. Advance Time
            current_time += TICK
            
            # 6. Safety Break
            if system_state == CPUState.IDLE and not ready_queue and next_arrival_idx == total_processes and current_process is None:
                # End of simulation
                break
                
        # Close final log
        if segment_start_time < current_time:
             pass # Optional: log final idle or state

    # --- Helper Methods ---

    def _is_preemptive(self, algo: str) -> bool:
        return algo in ["RR", "SRTF"]

    def _check_preemption(self, algo: str, current: Process, ready_queue: List[Process], quantum_used: int) -> bool:
        """
        Determines if the current running process should be preempted.
        """
        if not ready_queue:
            return False
            
        if algo == "RR":
            return quantum_used >= self.q_scaled
            
        elif algo == "SRTF":
            # Check if any process in ready queue has strictly lower remaining time
            shortest_in_queue = min(ready_queue, key=lambda p: p.remaining_time)
            return shortest_in_queue.remaining_time < current.remaining_time
            
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

    def _add_log(self, algo: str, start: int, end: int, pid: Optional[int], state: str):
        if start < end:
            self.logs.append(SimulationLog(algo, start, end, pid, state))

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

if __name__ == "__main__":
    # Example Usage matching definitions.py structure
    input_list = [
        (0.0, 6.0),
        (2.0, 4.0),
        (4.0, 2.0)
    ]
    scheduler = CPUScheduler(
        input_data=input_list, 
        q=2.0, 
        cs=1.0 # 0.5 Load + 0.5 Save
    )
    scheduler.run()
