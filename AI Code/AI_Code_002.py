from enum import Enum  # Importing Enum to define system states clearly

# Enum for different states the CPU/system can be in during simulation
class SystemState(Enum):
    IDLE = "IDLE"  # CPU is doing nothing
    CS_SAVE = "CS_SAVE"  # Context switch: saving the current process's state
    CS_LOAD = "CS_LOAD"  # Context switch: loading the next process's state
    EXECUTING = "EXECUTING"  # CPU is running a process

# Class to represent a single process with its attributes and metrics
class Process:
    def __init__(self, pid, arrival_time, burst_time):
        self.pid = pid  # Process ID (unique identifier)
        self.arrival_time = arrival_time  # When the process arrives in the system
        self.burst_time = burst_time  # Total CPU time needed
        self.remaining_time = burst_time  # Remaining CPU time (decreases as it executes)
        self.wait_time = 0  # Total time spent waiting in ready queue
        self.turnaround_time = 0  # Total time from arrival to completion
        self.response_time = -1  # Time from arrival to first CPU allocation
        self.start_time = -1  # When the process first starts executing
        self.completion_time = -1  # When the process finishes

# Main class for the CPU Scheduler simulator
class CPUScheduler:
    def __init__(self, processes_data, context_switch_time=0, time_quantum=5):
        # Calculate scale to convert floats to ints for precision (e.g., 10.25 becomes 1025 with scale=100)
        self.scale = self._calculate_scale(processes_data + [[context_switch_time, 0]])
        
        self.processes = []  # List of Process objects
        for i, (at, bt) in enumerate(processes_data):  # Create processes with scaled times
            scaled_at = int(at * self.scale)
            scaled_bt = int(bt * self.scale)
            self.processes.append(Process(i, scaled_at, scaled_bt))

        # Scale context switch and time quantum too
        self.context_switch_time = int(context_switch_time * self.scale)
        self.half_cs = self.context_switch_time // 2  # Assume CS time splits evenly for save/load

        self.time_quantum = int(time_quantum * self.scale)  # For RR, but not used in FCFS/SRTF yet
        self.time = 0  # Current simulation time (in scaled ticks)

        self.gantt = []  # List to store Gantt chart data: (start, end, label, pid)

        self.ready_queue = []  # Queue of processes ready to run
        self.current_process = None  # Currently running process
        self.current_quantum = 0  # Time slice used (for RR)
        self.system_state = SystemState.IDLE  # Initial state
        self.cs_progress = 0  # Progress counter for context switches (in ticks)
        self.outgoing_process = None  # Process being switched out during CS_SAVE

        # Sort processes by arrival time for efficient arrival checks
        self.processes.sort(key=lambda p: p.arrival_time)
        self.next_arr_index = 0  # Index for next process to arrive

    # Helper to find max decimal places in inputs for scaling
    def _calculate_scale(self, data):
        max_decimals = 0
        for at, bt in data:
            for val in [str(at), str(bt)]:
                if '.' in val:
                    max_decimals = max(max_decimals, len(val.split('.')[1]))
        return 10 ** max_decimals  # E.g., 2 decimals -> 100

    # Check if any processes arrive at the current time and add to ready queue
    def check_arrivals(self):
        while self.next_arr_index < len(self.processes) and self.processes[self.next_arr_index].arrival_time == self.time:
            p = self.processes[self.next_arr_index]
            self.ready_queue.append(p)
            self.next_arr_index += 1

    # Peek at the next process to run based on algorithm (without removing from queue)
    def get_next_process(self, algorithm):  
        if not self.ready_queue:
            return None
        
        queue_copy = self.ready_queue[:]  # Copy to sort without modifying original

        if algorithm == "FCFS":
            queue_copy.sort(key=lambda p: p.arrival_time)  # First come, first served: sort by arrival

        elif algorithm == "SRTF":
            queue_copy.sort(key=lambda p: p.remaining_time)  # Shortest remaining time first

        elif algorithm == "SJF":
            pass  # TODO: Sort by burst_time for non-preemptive SJF

        elif algorithm == "HRRN":
            pass  # TODO: Highest response ratio next

        elif algorithm == "Round-Robin":
            pass  # TODO: Typically FIFO for RR
        
        return queue_copy[0]  # Return the top one

    # Select and remove the next process from ready queue
    def select_next_process(self, algorithm):
        next_p = self.get_next_process(algorithm)
        if next_p:
            self.ready_queue.remove(next_p)
        return next_p

    # Check if a preemption should happen (only during execution, for preemptive algos)
    def check_preemption(self, algorithm):
        if self.system_state != SystemState.EXECUTING:
            return False
        would_be = self.get_next_process(algorithm)
        if not would_be:
            return False
        if algorithm == "SRTF" and would_be.remaining_time < self.current_process.remaining_time:
            return True
        # For FCFS, no preemption
        return False

    # Log a segment to the Gantt chart if it has duration
    def _log_gantt(self, start, end, label, pid=None):
        if start < end:
            self.gantt.append((start, end, label, pid))

    # Main simulation loop: runs until all processes are done
    def run(self, algorithm):
        segment_start = self.time  # Start of current Gantt segment
        current_label = "IDLE"  # Current activity label
        while True:
            self.check_arrivals()  # Check for new arrivals every tick

            # If preemption needed, start context switch out
            if self.check_preemption(algorithm):
                self._log_gantt(segment_start, self.time, current_label, self.current_process.pid if self.current_process else None)
                segment_start = self.time
                self.outgoing_process = self.current_process
                self.current_process = self.select_next_process(algorithm)
                if self.context_switch_time > 0:
                    self.system_state = SystemState.CS_SAVE
                    self.cs_progress = 0
                    current_label = "CS_SAVE"
                else:
                    self.system_state = SystemState.EXECUTING
                    current_label = "EXECUTING"
                self.current_quantum = 0
                self.time += 1  # Advance time
                continue  # Skip to next iteration

            # Increment wait time for all in ready queue (they're waiting)
            for p in self.ready_queue:
                p.wait_time += 1

            # Handle the current system state
            if self.system_state == SystemState.CS_LOAD:
                self.cs_progress += 1
                # For preemptive, check if abort needed (better process arrived)
                if algorithm == "SRTF" and self.check_preemption(algorithm):
                    self._log_gantt(segment_start, self.time, "CS_ABORTED", self.current_process.pid)
                    segment_start = self.time
                    self.ready_queue.append(self.current_process)  # Put back the one we were loading
                    self.current_process = None
                    self.system_state = SystemState.IDLE
                    self.cs_progress = 0
                    current_label = "IDLE"
                    self.time += 1
                    continue
                if self.cs_progress >= self.half_cs:  # CS load complete
                    self._log_gantt(segment_start, self.time, "CS_LOAD", self.current_process.pid)
                    segment_start = self.time
                    self.system_state = SystemState.EXECUTING
                    current_label = "EXECUTING"
                    self.cs_progress = 0
                    if self.current_process.start_time == -1:
                        self.current_process.start_time = self.time
                    if self.current_process.response_time == -1:
                        self.current_process.response_time = self.time - self.current_process.arrival_time

            elif self.system_state == SystemState.CS_SAVE:
                self.cs_progress += 1
                # For preemptive, check abort
                if algorithm == "SRTF" and self.check_preemption(algorithm):
                    self._log_gantt(segment_start, self.time, "CS_ABORTED", self.outgoing_process.pid)
                    segment_start = self.time
                    self.current_process = self.outgoing_process  # Resume the one we were saving
                    self.outgoing_process = None
                    self.system_state = SystemState.EXECUTING
                    self.cs_progress = 0
                    current_label = "EXECUTING"
                    self.time += 1
                    continue
                if self.cs_progress >= self.half_cs:  # CS save complete
                    self._log_gantt(segment_start, self.time, "CS_SAVE", self.outgoing_process.pid)
                    segment_start = self.time
                    if self.outgoing_process.remaining_time > 0:
                        self.ready_queue.append(self.outgoing_process)  # Put back if not done
                    self.outgoing_process = None
                    self.system_state = SystemState.CS_LOAD
                    self.cs_progress = 0
                    current_label = "CS_LOAD"

            elif self.system_state == SystemState.EXECUTING:
                self.current_process.remaining_time -= 1  # Execute one tick
                self.current_quantum += 1
                if self.current_process.remaining_time <= 0:  # Process finished
                    self._log_gantt(segment_start, self.time + 1, "EXECUTING", self.current_process.pid)  # Log up to next tick
                    segment_start = self.time + 1
                    self.current_process.completion_time = self.time + 1
                    self.current_process.turnaround_time = self.current_process.completion_time - self.current_process.arrival_time
                    self.current_process = None
                    self.system_state = SystemState.IDLE
                    current_label = "IDLE"

            elif self.system_state == SystemState.IDLE:
                if self.ready_queue:  # Start next process if available
                    self.current_process = self.select_next_process(algorithm)
                    if self.context_switch_time > 0:
                        self.system_state = SystemState.CS_LOAD
                        self.cs_progress = 0
                        current_label = "CS_LOAD"
                    else:
                        self.system_state = SystemState.EXECUTING
                        current_label = "EXECUTING"
                    self._log_gantt(segment_start, self.time, "IDLE", None)
                    segment_start = self.time

            self.time += 1  # Advance simulation time by one tick

            # Check if simulation is complete: no more arrivals, no ready, no current, idle
            if self.next_arr_index == len(self.processes) and not self.ready_queue and self.current_process is None and self.system_state == SystemState.IDLE:
                self._log_gantt(segment_start, self.time, current_label, None)
                break

# Example usage
processes_data = [[1, 6], [8, 5], [10.25, 2], [17.50, 3]]  # Will scale by 100 (2 decimals)

s = CPUScheduler(processes_data, context_switch_time=2)
s.run("SRTF")  # Or "FCFS"
print(s.gantt)  # Outputs scaled Gantt data; divide times by s.scale for original units