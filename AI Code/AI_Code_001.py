# import bpy
# import mathutils

class Process:
    def __init__(self, pid, arrival_time, burst_time):
        self.pid = pid  # Unique ID (0,1,2...)
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self.remaining_time = burst_time

        self.wait_time = 0  # Accumulated wait
        self.turnaround_time = 0  # To be calculated
        self.response_time = -1  # First CPU time - arrival
        self.start_time = -1  # When first started
        self.completion_time = -1  # When finished



import heapq  # For priority queues in SPN/HRRN/SRTF

class CPUScheduler:
    def __init__(self, processes_data, context_switch_time=0, time_quantum=5):
        # processes_data = [[burst, arrival], ...]
        # processes = [Process(i, at, bt), Process(i, at, bt), Process(i, at, bt), ... ]

        self.processes = [Process(i, at, bt) for i, (bt, at) in enumerate(processes_data)]

        self.context_switch_time = context_switch_time
        
        self.half_cs = context_switch_time // 2 if context_switch_time > 0 else 0  # Save/load duration; assume equal split
        
        self.time_quantum = time_quantum
        self.time = 0
        
        self.gantt = []  # List of (start, end, pid, event_type) e.g., "arrival", "execution", "save_context", "load_context", "idle"
        
        self.ready_queue = []  # List or heap

        self.current_process = None
        self.current_quantum = 0  # For RR
        self.in_switch = False
        self.switch_phase = None  # "save" or "load"
        self.switch_remaining = 0  # Ticks left in phase        
        self.outgoing_process = None  # For save phase




    def add_to_ready_queue(self, proc, algorithm):
        if algorithm in ["fcfs", "rr"]:
            self.ready_queue.append(proc)  # FIFO
        elif algorithm == "spn" or algorithm == "srtf":
            heapq.heappush(self.ready_queue, (proc.remaining_time, proc.pid, proc))  # Min-heap by remaining (SRTF uses remaining)
        elif algorithm == "hrrn":
            # HRRN needs dynamic ratio, so list and sort when selecting
            self.ready_queue.append(proc)

    def select_next_process(self, algorithm):
        if not self.ready_queue:
            self.current_process = None
            return

        if algorithm == "fcfs":
            self.current_process = self.ready_queue.pop(0)

        elif algorithm == "spn":
            _, _, proc = heapq.heappop(self.ready_queue)
            self.current_process = proc
            
        elif algorithm == "hrrn":
            # Calculate ratios
            available = []
            for proc in self.ready_queue:
                wait = self.time - proc.arrival_time
                ratio = (wait + proc.burst_time) / proc.burst_time  # Note: HRRN uses original burst, not remaining
                available.append((ratio, proc.pid, proc))
            if available:
                _, _, proc = max(available, key=lambda x: x[0])
                self.ready_queue.remove(proc)
                self.current_process = proc
        elif algorithm == "rr":
            self.current_process = self.ready_queue.pop(0)
        elif algorithm == "srtf":
            _, _, proc = heapq.heappop(self.ready_queue)
            self.current_process = proc

        # For preemptive, we might re-add if preempted later

    def is_preemption_needed(self, algorithm):
        if algorithm not in ["rr", "srtf"]:
            return False  # Non-preemptive

        if algorithm == "rr" and self.current_quantum >= self.time_quantum and self.ready_queue:
            return True

        if algorithm == "srtf" and self.ready_queue:
            # Check if top of queue has shorter remaining than current
            top_remaining, _, _ = self.ready_queue[0]
            if top_remaining < self.current_process.remaining_time:
                return True

        return False

    def start_context_switch(self, algorithm):
        if self.context_switch_time == 0:
            # Immediate select and run
            self.select_next_process(algorithm)
            return

        self.in_switch = True
        self.switch_phase = "save"
        self.switch_remaining = self.half_cs
        self.outgoing_process = self.current_process
        self.current_process = None  # Clear running
        self.gantt.append((self.time + 1, self.time + 1 + self.half_cs, self.outgoing_process.pid if self.outgoing_process else -1, "save_context"))  # +1 because tick just ended

        # For preemptive, during load, we'll check arrivals in the main loop (since ticks continue)

    def merge_gantt(self):
        # Optional: Merge consecutive "execution" for same proc to single entry for cleaner viz
        merged = []
        for entry in self.gantt:
            if merged and merged[-1][3] == entry[3] and merged[-1][2] == entry[2] and merged[-1][1] == entry[0]:
                merged[-1] = (merged[-1][0], entry[1], entry[2], entry[3])
            else:
                merged.append(entry)
        self.gantt = merged

    def get_metrics(self):
        WT = [p.wait_time for p in self.processes]
        TT = [p.turnaround_time for p in self.processes]
        RT = [p.response_time for p in self.processes]
        return WT, TT, RT

    def run(self, algorithm):
        # Sort processes by arrival for efficient checking
        self.processes.sort(key=lambda p: p.arrival_time)
        next_process_index = 0  # To add arrivals

        while True:
            # Step 1: Handle arrivals at current time
            while next_process_index < len(self.processes) and self.processes[next_process_index].arrival_time == self.time:
                proc = self.processes[next_process_index]
                self.add_to_ready_queue(proc, algorithm)
                self.gantt.append((self.time, self.time, proc.pid, "arrival"))
                next_process_index += 1

            # Step 2: Update waiting times for ready queue (except current)
            for proc in self.ready_queue:
                if proc != self.current_process:  # Current isn't waiting
                    proc.wait_time += 1

            # Step 3: Handle current state
            if self.in_switch:
                self.switch_remaining -= 1
                if self.switch_remaining == 0:
                    # Phase end
                    if self.switch_phase == "save":
                        # After save, select next
                        self.select_next_process(algorithm)
                        if self.current_process:
                            # Start load phase
                            self.switch_phase = "load"
                            self.switch_remaining = self.half_cs
                            self.gantt.append((self.time, self.time + self.half_cs, self.current_process.pid, "load_context"))
                        else:
                            # Idle if no next
                            self.in_switch = False
                    elif self.switch_phase == "load":
                        # Load done, start running
                        self.in_switch = False
                        if self.current_process.response_time == -1:
                            self.current_process.response_time = self.time - self.current_process.arrival_time
                        self.current_quantum = 0  # Reset for RR
            elif self.current_process:
                # Running state
                self.gantt.append((self.time, self.time + 1, self.current_process.pid, "execution"))
                self.current_process.remaining_time -= 1
                self.current_quantum += 1

                if self.current_process.start_time == -1:
                    self.current_process.start_time = self.time

                # Check for completion
                if self.current_process.remaining_time == 0:
                    self.current_process.completion_time = self.time + 1  # End of this tick
                    self.current_process.turnaround_time = self.current_process.completion_time - self.current_process.arrival_time
                    # Add execution event (accumulate if consecutive, but for simplicity, add per tick or batch)
                    # For Gantt, we'll batch later or add per segment
                    # Start switch if context >0
                    self.start_context_switch(algorithm)
                elif self.is_preemption_needed(algorithm):
                    # Preemptive check (e.g., RR quantum end or SRTF better arrival)
                    self.start_context_switch(algorithm)

            else:
                # Idle state: No current, no switch
                if self.ready_queue:
                    # Select and load directly (no outgoing, so no save)
                    self.select_next_process(algorithm)
                    if self.context_switch_time > 0:
                        self.in_switch = True
                        self.switch_phase = "load"
                        self.switch_remaining = self.half_cs  # Only load for first
                        self.gantt.append((self.time, self.time + self.half_cs, self.current_process.pid, "load_context"))
                    else:
                        # Immediate run
                        pass
                else:
                    # True idle
                    self.gantt.append((self.time, self.time + 1, -1, "idle"))

            # Advance time
            self.time += 1

            # Check if all done
            if all(p.completion_time != -1 for p in self.processes):
                break

        # Post-process Gantt to merge consecutive executions if needed (for cleaner Blender viz)
        self.merge_gantt()

        # Return data for Blender
        return self.gantt, self.get_metrics()





















# # Clear the default scene
# bpy.ops.object.select_all(action='SELECT')
# bpy.ops.object.delete(use_global=False)

# # Remove all materials from the file
# for mat in list(bpy.data.materials):
#     bpy.data.materials.remove(mat)

# # Create materials
# arrival_mat = bpy.data.materials.new(name="ArrivalGreen")
# arrival_mat.diffuse_color = (0, 1, 0, 1)

# execution_mat = bpy.data.materials.new(name="ExecutionBlue")
# execution_mat.diffuse_color = (0, 0, 1, 1)

# cs_mat = bpy.data.materials.new(name="ContextSwitchRed")
# cs_mat.diffuse_color = (1, 0, 0, 1)

# label_mat = bpy.data.materials.new(name="LabelBlack")
# label_mat.diffuse_color = (0, 0, 0, 1)









# algorithms = ["fcfs", "spn", "hrrn", "rr", "srtf"]
# z_offset = 0  # Starting Z position

# for algo_index, algo in enumerate(algorithms):
#     gantt, WT, TT, RT = getattr(scheduler, algo)()
    
#     # Create a new collection for this algorithm
#     coll = bpy.data.collections.new(algo.upper())
#     bpy.context.scene.collection.children.link(coll)
#     bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[coll.name]
    
#     # Find max time for axis
#     max_time = max(end for start, end, proc, event in gantt if event != "arrival")
    
#     # Create process labels (Y-axis)
#     for proc in range(len(scheduler.processes)):
#         bpy.ops.object.text_add(location=(-2, proc * 2, z_offset))
#         text_obj = bpy.context.object
#         text_obj.data.body = f"P{proc + 1}"
#         text_obj.data.size = 0.5
#         text_obj.data.materials.append(label_mat)
#         text_obj.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))  # Rotate to face camera
    
#     # Create algorithm title
#     bpy.ops.object.text_add(location=(max_time / 2, -2, z_offset))
#     title_obj = bpy.context.object
#     title_obj.data.body = algo.upper()
#     title_obj.data.size = 1.0
#     title_obj.data.materials.append(label_mat)
#     title_obj.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
    
#     # Visualize gantt entries
#     arrival_set = set()  # To avoid duplicate arrivals
#     for start, end, proc, event in gantt:


#         if event == "arrival":
#             key = (proc, start)
#             if key in arrival_set:
#                 continue
#             arrival_set.add(key)
#             bpy.ops.mesh.primitive_uv_sphere_add(radius=0.3, location=(start, proc * 2, z_offset))
#             obj = bpy.context.object
#             if len(obj.data.materials) == 0:
#                 obj.data.materials.append(arrival_mat)
#             else:
#                 obj.data.materials[0] = arrival_mat
        
#         elif event == "execution":
#             length = end - start
#             bpy.ops.mesh.primitive_cube_add(location=(start + length / 2, proc * 2, z_offset))
#             obj = bpy.context.object
#             obj.scale = (length / 2, 0.5, 0.5)
#             if len(obj.data.materials) == 0:
#                 obj.data.materials.append(execution_mat)
#             else:
#                 obj.data.materials[0] = execution_mat
            
#             # Add start time label
#             bpy.ops.object.text_add(location=(start, proc * 2 + 0.8, z_offset))
#             text_obj = bpy.context.object
#             text_obj.data.body = str(start)
#             text_obj.data.size = 0.4
#             text_obj.data.materials.append(label_mat)
#             text_obj.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
            
#             # Add end time label
#             bpy.ops.object.text_add(location=(end, proc * 2 + 0.8, z_offset))
#             text_obj = bpy.context.object
#             text_obj.data.body = str(end)
#             text_obj.data.size = 0.4
#             text_obj.data.materials.append(label_mat)
#             text_obj.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
        
#         elif event == "context_switch":
#             length = end - start
#             # Place context switches below processes at y = -1
#             bpy.ops.mesh.primitive_cube_add(location=(start + length / 2, -1, z_offset))
#             obj = bpy.context.object
#             obj.scale = (length / 2, 0.3, 0.3)
#             if len(obj.data.materials) == 0:
#                 obj.data.materials.append(cs_mat)
#             else:
#                 obj.data.materials[0] = cs_mat
            
#             # Add start/end labels for CS
#             bpy.ops.object.text_add(location=(start, -1 + 0.5, z_offset))
#             text_obj = bpy.context.object
#             text_obj.data.body = str(start)
#             text_obj.data.size = 0.4
#             text_obj.data.materials.append(label_mat)
#             text_obj.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
            
#             bpy.ops.object.text_add(location=(end, -1 + 0.5, z_offset))
#             text_obj = bpy.context.object
#             text_obj.data.body = str(end)
#             text_obj.data.size = 0.4
#             text_obj.data.materials.append(label_mat)
#             text_obj.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
    
#     # Add metrics table as text objects
#     metrics_x = max_time + 5
#     metrics_y_start = len(scheduler.processes) * 2
#     # Headers
#     bpy.ops.object.text_add(location=(metrics_x, metrics_y_start, z_offset))
#     header = bpy.context.object
#     header.data.body = "Proc | WT | TT | RT"
#     header.data.size = 0.5
#     header.data.materials.append(label_mat)
#     header.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
    
#     for proc in range(len(WT)):
#         bpy.ops.object.text_add(location=(metrics_x, metrics_y_start - (proc + 1) * 1, z_offset))
#         row = bpy.context.object
#         row.data.body = f"P{proc+1}  | {WT[proc]} | {TT[proc]} | {RT[proc]}"
#         row.data.size = 0.4
#         row.data.materials.append(label_mat)
#         row.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
    
#     # Averages
#     avg_wt = sum(WT) / len(WT)
#     avg_tt = sum(TT) / len(TT)
#     avg_rt = sum(RT) / len(RT)
#     bpy.ops.object.text_add(location=(metrics_x, metrics_y_start - (len(WT) + 2), z_offset))
#     avg_text = bpy.context.object
#     avg_text.data.body = f"Avg: | {avg_wt:.2f} | {avg_tt:.2f} | {avg_rt:.2f}"
#     avg_text.data.size = 0.5
#     avg_text.data.materials.append(label_mat)
#     avg_text.rotation_euler = (mathutils.Euler((1.5708, 0, 0)))
    
#     # Offset for next algorithm in Z
#     z_offset += 15  # Space between algorithm visualizations





# # # Add a camera and light for viewing
# # bpy.ops.object.camera_add(location=(max_time / 2, 0, z_offset + 20))
# # camera = bpy.context.object
# # camera.rotation_euler = (0, 0, 0)  # Point down

# # bpy.ops.object.light_add(type='SUN', location=(0, 0, 50))






# # Set render engine to Cycles for better materials
# bpy.context.scene.render.engine = 'CYCLES'