from typing import List, Optional, Dict
from dataclasses import dataclass, field
from definitions import (
    SchedulerMode, Process, ProcessState, GanttEntry,
    validate_input_and_determine_scheduler_mode, scale_input_time
)


@dataclass
class Scheduler:
    input_data_list: List
    cs_ticks: int
    q_ticks: int
    mode: SchedulerMode
    time_scale: int

    half_cs_ticks: int = field(init=False)
    gantt_entries: Dict[str, List[GanttEntry]] = field(default_factory=dict)
    processes: List[Process] = field(init=False, default_factory=list)

    def __post_init__(self):
        self.half_cs_ticks = max(1, (self.cs_ticks + 1) // 2)   # improved rounding
        self.input_data_list.sort(key=lambda x: x[0])

    def run(self):
        if self.mode is SchedulerMode.PROCESS:
            algorithms = ["FCFS", "SPN", "HRRN", "RR", "SRTF"]
        elif self.mode is SchedulerMode.MLQ:
            algorithms = ["MLQ"]
        else:
            algorithms = ["FIFO", "SJF", "Random"]

        for algo in algorithms:
            self._run_single_algorithm(algo)

        self.generate_gantt_and_metrics()

    def _run_single_algorithm(self, algorithm: str):
        print(f"\n{'='*25} Running {algorithm} {'='*25}")

        self._reset_simulation_objects()
        processes = self.processes

        current_time = 0
        next_arrival_idx = 0
        completed_count = 0
        total = len(processes)

        current_process: Optional[Process] = None
        outgoing_process: Optional[Process] = None
        cs_progress = 0
        system_state = "IDLE"
        segment_start = 0
        current_quantum = 0

        ready_queue: List[Process] = []
        self.gantt_entries[algorithm] = []

        def log_segment(end_time: int, label: str, pid: Optional[int] = None):
            if segment_start >= end_time:
                return
            s = segment_start / self.time_scale
            e = end_time / self.time_scale
            self.gantt_entries[algorithm].append(GanttEntry(algorithm, s, e, pid, label))

        while completed_count < total:
            # 1. Arrivals
            while next_arrival_idx < total and processes[next_arrival_idx].arrival_time <= current_time:
                p = processes[next_arrival_idx]
                p.state = ProcessState.READY
                ready_queue.append(p)
                next_arrival_idx += 1

            # 2. Preemption
            if system_state == "EXECUTING" and current_process:
                if self._should_preempt(algorithm, current_process, ready_queue, current_quantum):
                    log_segment(current_time, "EXECUTING", current_process.pid)
                    segment_start = current_time
                    outgoing_process = current_process
                    current_process = None
                    if self.cs_ticks > 0:
                        system_state = "CS_SAVE"
                        cs_progress = 0
                    else:
                        outgoing_process.state = ProcessState.READY
                        ready_queue.append(outgoing_process)
                        outgoing_process = None
                        system_state = "IDLE"

            # 3. Waiting time
            for p in ready_queue:
                p.wait_time += 1

            # 4. State machine
            if system_state == "CS_LOAD":
                cs_progress += 1
                if cs_progress >= self.half_cs_ticks:
                    if current_process is None:          # ← Safety guard (fixes the crash)
                        system_state = "IDLE"
                        cs_progress = 0
                        continue
                    log_segment(current_time + 1, "CS_LOAD", current_process.pid)
                    segment_start = current_time + 1
                    system_state = "EXECUTING"
                    current_process.state = ProcessState.RUNNING
                    current_quantum = 0
                    if current_process.start_time == -1:
                        current_process.start_time = current_time + 1
                        current_process.response_time = current_process.start_time - current_process.arrival_time

            elif system_state == "CS_SAVE":
                cs_progress += 1
                if cs_progress >= self.half_cs_ticks:
                    if outgoing_process is None:
                        system_state = "IDLE"
                        cs_progress = 0
                        continue
                    log_segment(current_time + 1, "CS_SAVE", outgoing_process.pid)
                    segment_start = current_time + 1
                    if outgoing_process.remaining_time > 0:
                        outgoing_process.state = ProcessState.READY
                        ready_queue.append(outgoing_process)
                    else:
                        outgoing_process.state = ProcessState.TERMINATED
                    outgoing_process = None
                    system_state = "CS_LOAD"
                    cs_progress = 0

            elif system_state == "EXECUTING":
                current_process.remaining_time -= 1
                current_quantum += 1
                if current_process.remaining_time <= 0:
                    log_segment(current_time + 1, "EXECUTING", current_process.pid)
                    segment_start = current_time + 1
                    current_process.completion_time = current_time + 1
                    current_process.turnaround_time = current_process.completion_time - current_process.arrival_time
                    current_process.state = ProcessState.TERMINATED
                    completed_count += 1
                    outgoing_process = current_process
                    current_process = None
                    if self.cs_ticks > 0:
                        system_state = "CS_SAVE"
                        cs_progress = 0
                    else:
                        system_state = "IDLE"

            elif system_state == "IDLE":
                candidate = self._select_next_process(algorithm, ready_queue, current_time)
                if candidate:
                    if current_time > segment_start:
                        log_segment(current_time, "IDLE")
                        segment_start = current_time
                    current_process = candidate
                    if self.cs_ticks > 0:
                        system_state = "CS_LOAD"
                        cs_progress = 0
                    else:
                        system_state = "EXECUTING"
                        current_process.state = ProcessState.RUNNING
                        current_quantum = 0
                        if current_process.start_time == -1:
                            current_process.start_time = current_time
                            current_process.response_time = current_process.start_time - current_process.arrival_time

            current_time += 1

            # Termination check
            if (next_arrival_idx >= total and not ready_queue and
                current_process is None and system_state == "IDLE"):
                break

        if segment_start < current_time:
            log_segment(current_time, "IDLE")

    # === Helper methods (unchanged) ===
    def _should_preempt(self, algo: str, current: Process, ready: List[Process], quantum_used: int) -> bool:
        if not ready: return False
        if algo in ("FCFS", "SPN", "HRRN"): return False
        if algo == "RR": return quantum_used >= self.q_ticks
        if algo == "SRTF":
            return min(ready, key=lambda p: p.remaining_time).remaining_time < current.remaining_time
        return False

    def _select_next_process(self, algo: str, ready_queue: List[Process], current_time: int) -> Optional[Process]:
        if not ready_queue: return None
        if algo in ("FCFS", "RR"):
            return ready_queue.pop(0)
        elif algo in ("SPN", "SRTF"):
            key = (lambda p: p.burst_time) if algo == "SPN" else (lambda p: p.remaining_time)
            idx = min(range(len(ready_queue)), key=lambda i: key(ready_queue[i]))
            return ready_queue.pop(idx)
        elif algo == "HRRN":
            best = self._get_hrrn_candidate(ready_queue, current_time)
            ready_queue.remove(best)
            return best
        return ready_queue.pop(0)

    def _get_hrrn_candidate(self, ready_queue: List[Process], current_time: int) -> Process:
        best = None
        max_ratio = -1.0
        for p in ready_queue:
            ratio = (current_time - p.arrival_time + p.burst_time) / p.burst_time
            if ratio > max_ratio:
                max_ratio = ratio
                best = p
        return best

    def _reset_simulation_objects(self):
        if self.mode is SchedulerMode.PROCESS:
            self.processes = [
                Process(pid=i, arrival_time=at, burst_time=bt)
                for i, (at, bt) in enumerate(self.input_data_list)
            ]
        else:
            self.processes = []

    def generate_gantt_and_metrics(self):
        for algo, entries in self.gantt_entries.items():
            print(f"\n{'='*30} {algo} REPORT {'='*30}")

            procs = sorted(self.processes, key=lambda p: p.pid)

            print(f"{'PID':<4} {'AT':<8} {'BT':<8} {'CT':<8} {'TAT':<8} {'WT':<8} {'RT':<8}")
            print("-" * 60)

            total_tat = total_wt = total_rt = 0.0
            for p in procs:
                tat = p.turnaround_time / self.time_scale
                wt = p.wait_time / self.time_scale
                rt = p.response_time / self.time_scale if p.response_time >= 0 else 0.0

                total_tat += tat
                total_wt += wt
                total_rt += rt

                print(f"{p.pid:<4} {p.arrival_time/self.time_scale:<8.2f} "
                      f"{p.burst_time/self.time_scale:<8.2f} "
                      f"{p.completion_time/self.time_scale:<8.2f} "
                      f"{tat:<8.2f} {wt:<8.2f} {rt:<8.2f}")

            n = len(procs)
            if n > 0:
                print("-" * 60)
                print(f"AVG{'':<28} {total_tat/n:<8.2f} {total_wt/n:<8.2f} {total_rt/n:<8.2f}")

            print("\nGantt Chart:")
            for e in entries:
                pid_str = f"P{e.pid}" if e.pid is not None else ""
                print(f"{e.start:7.2f} → {e.end:7.2f}  |  {e.label:<12} {pid_str}")


# ====================== RUN ======================
if __name__ == "__main__":
    input_list = [[1, 6], [80000, 50000], [102500, 20000], [175000, 30000]]
    input_quantum_time = 3.0
    input_cs_time = 1.0

    scheduler_mode = validate_input_and_determine_scheduler_mode(input_list, input_quantum_time, input_cs_time)
    data_list_scaled, q_scaled, cs_scaled, time_scale = scale_input_time(
        input_list, input_quantum_time, input_cs_time, scheduler_mode
    )

    scheduler = Scheduler(
        input_data_list=data_list_scaled,
        cs_ticks=cs_scaled,
        q_ticks=q_scaled,
        mode=scheduler_mode,
        time_scale=time_scale
    )

    scheduler.run()