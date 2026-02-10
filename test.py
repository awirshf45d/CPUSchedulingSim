from enum import Enum
import decimal  # For precise decimal counting

class SystemState(Enum):
    IDLE = "IDLE"
    CS_SAVE = "CS_SAVE"
    CS_LOAD = "CS_LOAD"
    EXECUTING = "EXECUTING"

class Process:
    def __init__(self, pid, arrival_time, burst_time):
        self.pid = pid
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.remaining_time = burst_time
        self.wait_time = 0
        self.turnaround_time = 0
        self.response_time = -1
        self.start_time = -1
        self.completion_time = -1

class CPUScheduler:
    def __init__(self, processes_data, context_switch_time=0, time_quantum=5):
        self.scale = self._calculate_scale(processes_data + [[context_switch_time, 0]])  # Include cs for precision
        self.processes = []
        for i, (at, bt) in enumerate(processes_data):
            scaled_at = int(decimal.Decimal(str(at)) * self.scale)
            scaled_bt = int(decimal.Decimal(str(bt)) * self.scale)
            self.processes.append(Process(i, scaled_at, scaled_bt))

        self.context_switch_time = int(decimal.Decimal(str(context_switch_time)) * self.scale)
        self.half_cs = self.context_switch_time // 2

        self.time_quantum = int(decimal.Decimal(str(time_quantum)) * self.scale)
        self.time = 0

        self.gantt = []  # (start, end, label, pid)

        self.ready_queue = []
        self.current_process = None
        self.current_quantum = 0
        self.system_state = SystemState.IDLE
        self.cs_progress = 0  # Incremented each tick during CS
        self.outgoing_process = None

        self.processes.sort(key=lambda p: p.arrival_time)
        self.next_arr_index = 0

    def _calculate_scale(self, data):
        max_decimals = 0
        for at, bt in data:
            for val in [str(at), str(bt)]:
                if '.' in val:
                    max_decimals = max(max_decimals, len(val.split('.')[1]))
        return decimal.Decimal(10) ** max_decimals

    def check_arrivals(self):
        while self.next_arr_index < len(self.processes) and self.processes[self.next_arr_index].arrival_time == self.time:
            p = self.processes[self.next_arr_index]
            self.ready_queue.append(p)
            self.next_arr_index += 1

    def get_next_process(self, algorithm):  # Peek without removing
        if not self.ready_queue:
            return None
        queue_copy = self.ready_queue[:]
        if algorithm == "FCFS":
            queue_copy.sort(key=lambda p: p.arrival_time)
        elif algorithm == "SJF":
            queue_copy.sort(key=lambda p: p.burst_time)
        elif algorithm == "HRRN":
            for p in queue_copy:
                executed = p.burst_time - p.remaining_time
                p.wait_time = self.time - p.arrival_time - executed
            queue_copy.sort(key=lambda p: -((p.wait_time + p.burst_time) / p.burst_time) if p.burst_time > 0 else 0)
        elif algorithm == "Round-Robin":
            queue_copy.sort(key=lambda p: p.arrival_time)  # FIFO for RR
        elif algorithm == "SRTF":
            queue_copy.sort(key=lambda p: p.remaining_time)
        return queue_copy[0]

    def select_next_process(self, algorithm):
        next_p = self.get_next_process(algorithm)
        if next_p:
            self.ready_queue.remove(next_p)
        return next_p

    def check_preemption(self, algorithm):
        if self.system_state != SystemState.EXECUTING or algorithm not in ["SRTF", "HRRN", "Round-Robin"]:
            return False
        would_be = self.get_next_process(algorithm)
        if not would_be:
            return False
        if algorithm == "SRTF" and would_be.remaining_time < self.current_process.remaining_time:
            return True
        elif algorithm == "HRRN":
            # Similar, but use HRRN ratio
            pass  # Fill if needed
        elif algorithm == "Round-Robin" and self.current_quantum >= self.time_quantum:
            return True
        return False

    def _log_gantt(self, start, end, label, pid=None):
        if start < end:
            self.gantt.append((start, end, label, pid))

    def run(self, algorithm):
        segment_start = self.time
        current_label = "IDLE"
        while True:
            self.check_arrivals()  # Green: always check arrivals

            # Yellow-ish: check if we need to preempt or select (but don't always select)
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
                self.time += 1
                continue

            # Update waits
            for p in self.ready_queue:
                p.wait_time += 1

            # Handle state
            if self.system_state == SystemState.CS_LOAD:
                self.cs_progress += 1
                # Check abort
                if algorithm in ["SRTF", "HRRN"] and self.check_preemption(algorithm):  # Adapt for RR if needed
                    self._log_gantt(segment_start, self.time, "CS_ABORTED", self.current_process.pid)
                    segment_start = self.time
                    self.ready_queue.append(self.current_process)  # Put back incoming
                    self.current_process = None
                    self.system_state = SystemState.IDLE
                    self.cs_progress = 0
                    current_label = "IDLE"
                    self.time += 1
                    continue
                if self.cs_progress >= self.half_cs:
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
                # Check abort
                if algorithm in ["SRTF", "HRRN"] and self.check_preemption(algorithm):
                    self._log_gantt(segment_start, self.time, "CS_ABORTED", self.outgoing_process.pid)
                    segment_start = self.time
                    self.current_process = self.outgoing_process  # Resume outgoing
                    self.outgoing_process = None
                    self.system_state = SystemState.EXECUTING
                    self.cs_progress = 0
                    current_label = "EXECUTING"
                    self.time += 1
                    continue
                if self.cs_progress >= self.half_cs:
                    self._log_gantt(segment_start, self.time, "CS_SAVE", self.outgoing_process.pid)
                    segment_start = self.time
                    if self.outgoing_process.remaining_time > 0:
                        self.ready_queue.append(self.outgoing_process)
                    self.outgoing_process = None
                    self.system_state = SystemState.CS_LOAD
                    self.cs_progress = 0
                    current_label = "CS_LOAD"

            elif self.system_state == SystemState.EXECUTING:
                self.current_process.remaining_time -= 1
                self.current_quantum += 1
                if self.current_process.remaining_time <= 0:
                    self._log_gantt(segment_start, self.time + 1, "EXECUTING", self.current_process.pid)  # +1 since time advances after
                    segment_start = self.time + 1
                    self.current_process.completion_time = self.time + 1
                    self.current_process.turnaround_time = self.current_process.completion_time - self.current_process.arrival_time
                    self.current_process = None
                    self.system_state = SystemState.IDLE
                    current_label = "IDLE"

            elif self.system_state == SystemState.IDLE:
                if self.ready_queue:
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

            self.time += 1

            # Termination check
            if self.next_arr_index == len(self.processes) and not self.ready_queue and self.current_process is None and self.system_state == SystemState.IDLE:
                self._log_gantt(segment_start, self.time, current_label, None)
                break

# Example
processes_data = [[1, 6], [8, 5], [10.25, 2], [17.50, 3]]  # Will scale by 100 (2 decimals)

s = CPUScheduler(processes_data, context_switch_time=2)
s.run("SRTF")
print(s.gantt)  # Scaled times; divide by s.scale for original