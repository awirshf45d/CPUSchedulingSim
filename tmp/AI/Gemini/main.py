import math
from typing import List, Optional
from definitions import (
    Process, ReadyQueue, SystemState, Algorithm, 
    GanttSegment, TIME_SCALE, PID_PREFIX
)

class SchedulerSimulator:
    def __init__(self, 
                 input_data: List[List[float]], 
                 cs_time_sec: float, 
                 quantum_sec: float,
                 queues_config: List[dict]):
        
        # 1. Initialization & Scaling
        self.cs_time_ticks = int(cs_time_sec * TIME_SCALE)
        self.half_cs_ticks = self.cs_time_ticks // 2
        
        # Parse inputs: [[Arrival, Burst, (Optional Priority)]]
        self.pending_inputs = []
        for idx, entry in enumerate(input_data):
            arr = int(entry[0] * TIME_SCALE)
            burst = int(entry[1] * TIME_SCALE)
            prio = int(entry[2]) if len(entry) > 2 else 0 # Default priority 0
            # Store as simple struct/dict for now, convert to Process on arrival
            self.pending_inputs.append({
                'id': idx + 1,
                'arr': arr,
                'burst': burst,
                'prio': prio
            })
        
        # Sort inputs by arrival time
        self.pending_inputs.sort(key=lambda x: x['arr'])
        
        # Setup Queues
        self.ready_queues: List[ReadyQueue] = []
        for q_cfg in queues_config:
            # Scale quantum if present
            q_quantum = int(q_cfg.get('quantum', quantum_sec) * TIME_SCALE)
            self.ready_queues.append(ReadyQueue(
                priority_band=q_cfg['priority'],
                algorithm=q_cfg['algorithm'],
                quantum_ticks=q_quantum
            ))
        # Sort queues by priority (lower number = higher priority)
        self.ready_queues.sort(key=lambda q: q.priority_band)

        # Simulation State
        self.current_time = 0
        self.segment_start = 0
        self.system_state = SystemState.IDLE
        self.current_label = "IDLE"
        
        self.current_process: Optional[Process] = None
        self.outgoing_process: Optional[Process] = None
        
        self.cs_progress = 0
        self.cs_phase = None # "SAVE" or "LOAD"
        
        self.all_processes: List[Process] = [] # To store all created processes for metrics
        self.gantt_log: List[GanttSegment] = []
        self.next_input_idx = 0

    def run(self):
        print(f"--- Starting Simulation [Scale: 1s={TIME_SCALE} ticks] ---")
        
        while True:
            # --- 1. Handle Arrivals ---
            while self.next_input_idx < len(self.pending_inputs):
                nxt = self.pending_inputs[self.next_input_idx]
                if nxt['arr'] == self.current_time:
                    # Create Process
                    new_proc = Process(
                        pid=nxt['id'],
                        arrival_time_ticks=nxt['arr'],
                        burst_time_ticks=nxt['burst'],
                        priority=nxt['prio']
                    )
                    self.all_processes.append(new_proc)
                    
                    # Find matching queue
                    queue = self.find_queue(new_proc.priority)
                    queue.add_process(new_proc)
                    
                    # print(f"Time {self.current_time}: Process P{new_proc.pid} Arrived.")
                    self.next_input_idx += 1
                elif nxt['arr'] < self.current_time:
                     # This shouldn't happen if sorted, but just in case
                     self.next_input_idx += 1
                else:
                    break # Next arrival is in future

            # --- 2. Check for Preemption (If Executing) ---
            if self.system_state == SystemState.EXECUTING and self.current_process:
                should_preempt, reason = self.check_preemption(self.current_process)
                
                if should_preempt:
                    # Log current work segment
                    self.log_segment()
                    self.segment_start = self.current_time
                    
                    # Handle outgoing
                    self.outgoing_process = self.current_process
                    
                    # Determine next (removes from queue)
                    best_q, best_p = self.get_highest_priority_process()
                    self.current_process = best_p
                    best_q.processes.remove(best_p)
                    
                    if self.cs_time_ticks > 0:
                        self.system_state = SystemState.CS_SAVE
                        self.cs_phase = "SAVE"
                        self.cs_progress = 0
                        self.current_label = "CS_SAVE"
                    else:
                        # Instant switch
                        self.system_state = SystemState.EXECUTING
                        self.current_label = f"EXECUTING"
                    
                    # Advance time immediately for this tick after state change decision?
                    # Backbone says: Advance current_time by 1 and Continue
                    self.current_time += 1
                    continue 

            # --- 3. Update Waiting Metrics ---
            for q in self.ready_queues:
                for p in q.processes:
                    p.wait_time_ticks += 1

            # --- 4. Handle Current System State ---
            match self.system_state:
                
                case SystemState.CS_LOAD:
                    self.cs_progress += 1
                    
                    # Check CS Abort (if high priority arrives during load)
                    # Note: Complex, simplified here to standard load completion
                    
                    if self.cs_progress >= self.half_cs_ticks:
                        self.log_segment() # Log the Load
                        self.segment_start = self.current_time # +1 implicitly at end of loop
                        
                        self.system_state = SystemState.EXECUTING
                        self.current_label = "EXECUTING"
                        self.cs_progress = 0
                        self.cs_phase = None
                        
                        # Set start time if first run
                        if self.current_process.start_time_ticks is None:
                            self.current_process.start_time_ticks = self.current_time

                case SystemState.CS_SAVE:
                    self.cs_progress += 1
                    
                    if self.cs_progress >= self.half_cs_ticks:
                        self.log_segment() # Log the Save
                        self.segment_start = self.current_time
                        
                        # Process outgoing
                        if self.outgoing_process.remaining_time_ticks > 0:
                            # Return to queue
                            q = self.find_queue(self.outgoing_process.priority)
                            q.add_process(self.outgoing_process)
                        else:
                            # It finished exactly as preemption happened? Rare but possible.
                            self.outgoing_process.completion_time_ticks = self.current_time
                        
                        self.outgoing_process = None
                        
                        self.system_state = SystemState.CS_LOAD
                        self.cs_phase = "LOAD"
                        self.cs_progress = 0
                        self.current_label = "CS_LOAD"

                case SystemState.EXECUTING:
                    # Work done
                    self.current_process.remaining_time_ticks -= 1
                    
                    # Check Round Robin Quantum Expiry
                    # Find queue for current process to get quantum
                    curr_q = self.find_queue(self.current_process.priority)
                    
                    time_slice_expired = False
                    if curr_q.algorithm == Algorithm.RR and curr_q.quantum_ticks > 0:
                        # Simple RR logic: track duration since segment start
                        duration = self.current_time - self.segment_start
                        # Note: +1 because we just did work this tick
                        if (duration + 1) >= curr_q.quantum_ticks and self.current_process.remaining_time_ticks > 0:
                            time_slice_expired = True

                    if self.current_process.remaining_time_ticks <= 0:
                        # --- Process Finished ---
                        self.log_segment(force_end_tick=self.current_time + 1)
                        self.segment_start = self.current_time + 1
                        
                        self.current_process.completion_time_ticks = self.current_time + 1
                        self.current_process = None
                        self.system_state = SystemState.IDLE
                        self.current_label = "IDLE"
                        
                    elif time_slice_expired:
                        # --- Quantum Expired (Preemption) ---
                        # Similar logic to standard preemption but forced by Quantum
                        self.log_segment(force_end_tick=self.current_time + 1)
                        self.segment_start = self.current_time + 1
                        
                        self.outgoing_process = self.current_process
                        
                        # Pick next (could be same if only one exists)
                        # Put current back first? Standard RR puts back at tail immediately
                        curr_q.processes.append(self.outgoing_process) # Back of line
                        
                        # Now pick best
                        best_q, best_p = self.get_highest_priority_process()
                        
                        if best_p == self.outgoing_process:
                             # Same process picked again, no CS needed usually, or minimal
                             self.current_process = best_p
                             best_q.processes.remove(best_p)
                             self.system_state = SystemState.EXECUTING # Continue
                             self.outgoing_process = None
                        else:
                            # Different process, do CS
                            self.current_process = best_p
                            best_q.processes.remove(best_p)
                            
                            if self.cs_time_ticks > 0:
                                self.system_state = SystemState.CS_SAVE
                                self.cs_phase = "SAVE"
                                self.cs_progress = 0
                                self.current_label = "CS_SAVE"
                            else:
                                self.system_state = SystemState.EXECUTING
                                self.current_label = "EXECUTING"

                case SystemState.IDLE:
                    # Try to find work
                    best_q, best_p = self.get_highest_priority_process()
                    
                    if best_p:
                        self.log_segment() # Log idle time
                        self.segment_start = self.current_time
                        
                        self.current_process = best_p
                        best_q.processes.remove(best_p)
                        
                        if self.cs_time_ticks > 0:
                            self.system_state = SystemState.CS_LOAD
                            self.cs_phase = "LOAD"
                            self.cs_progress = 0
                            self.current_label = "CS_LOAD"
                        else:
                            self.system_state = SystemState.EXECUTING
                            self.current_label = "EXECUTING"

            # --- 5. Advance Time ---
            self.current_time += 1
            
            # --- 6. Termination Check ---
            # Idle, No current process, Input exhausted, All queues empty
            queues_empty = all(len(q.processes) == 0 for q in self.ready_queues)
            if (self.system_state == SystemState.IDLE and 
                self.current_process is None and 
                self.next_input_idx >= len(self.pending_inputs) and 
                queues_empty):
                
                self.log_segment() # Log final IDLE if any
                break

        print("--- Simulation Finished ---")
        self.generate_report()

    # --- Helpers ---

    def find_queue(self, priority: int) -> ReadyQueue:
        for q in self.ready_queues:
            if q.priority_band == priority:
                return q
        # Fallback to first queue if mismatch
        return self.ready_queues[0]

    def get_highest_priority_process(self) -> (Optional[ReadyQueue], Optional[Process]):
        """Finds the highest priority non-empty queue and peeks its best process."""
        for q in self.ready_queues:
            proc = q.peek_next()
            if proc:
                return q, proc
        return None, None

    def check_preemption(self, current_proc: Process) -> (bool, str):
        """
        Returns (True, Reason) if current process should be preempted.
        """
        curr_q = self.find_queue(current_proc.priority)
        best_q, best_p = self.get_highest_priority_process()
        
        if not best_p:
            return False, ""
            
        # 1. Higher Priority Band Preemption (Preemptive Priority Scheduling)
        if best_q.priority_band < curr_q.priority_band:
            return True, "Higher Priority Band"
            
        # 2. Same Band Preemption (SRTF)
        if best_q == curr_q and curr_q.algorithm == Algorithm.SRTF:
            # If the new best process has strictly less time than current remaining
            if best_p.remaining_time_ticks < current_proc.remaining_time_ticks:
                return True, "SRTF Optimization"
        
        return False, ""

    def log_segment(self, force_end_tick: int = None):
        end = force_end_tick if force_end_tick is not None else self.current_time
        if end > self.segment_start:
            pid = self.current_process.pid if self.current_process else None
            # If CS, use outgoing or incoming PID depending on phase? 
            # Usually CS is System time, but for visuals we might attach to PID.
            # Backbone says: label with optional _P{pid}
            
            lbl = self.current_label
            
            # Add segment
            self.gantt_log.append(GanttSegment(
                start_tick=self.segment_start,
                end_tick=end,
                label=lbl,
                pid=pid
            ))

    def generate_report(self):
        # 1. Metrics Table
        print("\n" + "="*60)
        print(f"{'PID':<5} | {'Arr(s)':<8} | {'Burst(s)':<8} | {'Wait(s)':<8} | {'TA(s)':<8}")
        print("-" * 60)
        
        total_wait = 0
        total_ta = 0
        
        # Sort by PID for clean output
        self.all_processes.sort(key=lambda x: x.pid)
        
        for p in self.all_processes:
            arr = p.arrival_time_ticks / TIME_SCALE
            bur = p.burst_time_ticks / TIME_SCALE
            wait = p.wait_time_ticks / TIME_SCALE
            ta = p.turnaround_time_ticks / TIME_SCALE
            
            total_wait += wait
            total_ta += ta
            
            print(f"P{p.pid:<4} | {arr:<8.4f} | {bur:<8.4f} | {wait:<8.4f} | {ta:<8.4f}")
            
        avg_wait = total_wait / len(self.all_processes) if self.all_processes else 0
        avg_ta = total_ta / len(self.all_processes) if self.all_processes else 0
        
        print("-" * 60)
        print(f"Average Wait Time: {avg_wait:.5f} sec")
        print(f"Average Turnaround Time: {avg_ta:.5f} sec")
        
        
        # 2. Gantt Chart (Text Based)
        print("\n--- Gantt Chart Log ---")
        for seg in self.gantt_log:
            start_s = seg.start_tick / TIME_SCALE
            end_s = seg.end_tick / TIME_SCALE
            label = seg.label
            p_str = f"P{seg.pid}" if seg.pid else ""
            print(f"[{start_s:07.4f} -> {end_s:07.4f}] : {label} {p_str}")
        print("\n\n\n\n\n")
        print(self.gantt_log)

# --- Entry Point ---
if __name__ == "__main__":
    
    # Configuration Example (Matches your backbone input roughly)
    # [Arrival, Burst, Priority(optional)]
    inputs = [[6, 1], [10, 7], [2, 9], [3, 25]]
    
    # Queue Config
    # Example: 2 Levels. Level 0 is RR, Level 1 is FCFS
    q_config = [
        {'priority': 0, 'algorithm': Algorithm.RR, 'quantum': 3.0},
        # {'priority': 1, 'algorithm': Algorithm.FCFS} 
    ]
    
    sim = SchedulerSimulator(
        input_data=inputs,
        cs_time_sec=0.4, # Example CS time
        quantum_sec=3.0,
        queues_config=q_config
    )
    
    sim.run()
