import bpy
import math, copy

# specifying the font path
font_path = r"//Fonts/JustAnotherHand-Regular.ttf"

# load the font file
font = bpy.data.fonts.load(font_path)


# making all object rotation modes into euler xyz (to make sure transforms are correct)
for obj in bpy.data.objects:
    if obj.rotation_mode != 'XYZ':
        obj.rotation_mode = 'XYZ'



gantt = [
    (0, 0, 0, 'PROCESS_ARRIVAL'),
    (0, 1, 0, 'CS_LOAD'),
    (1, 6, 0, 'EXECUTING'),
    (2, 2, 1, 'PROCESS_ARRIVAL'),
    (6, 7, 0, 'CS_SAVE'),
    (7, 8, 1, 'CS_LOAD'),
    (9, 9, 2, 'PROCESS_ARRIVAL'),
    (8, 14, 1, 'EXECUTING'),
    (14, 15, 1, 'CS_SAVE'),
    (15, 16, 0, 'CS_LOAD'),
    (16, 18, 0, 'EXECUTING'),
    (18, 19, 0, 'CS_SAVE'),
    (19, 20, 2, 'CS_LOAD'),
    (20, 20, 3, 'PROCESS_ARRIVAL'),
    (20, 21, 2, 'EXECUTING'),
    (21, 22, 2, 'CS_SAVE'),
    (22, 23, 1, 'CS_LOAD'),
    (23, 26, 1, 'EXECUTING'),
    (26, 27, 1, 'CS_SAVE'),
    (27, 28, 3, 'CS_LOAD'),
    (28, 29, 3, 'EXECUTING'),
    (29, 30, 3, 'CS_SAVE')
]


class Process:
    def __init__(self, pid=0, arrival_time=0, burst_time=8, _process_ready_queue_id=0, category=None, priority=0, remaining_time=0, wait_time=0, turnaround_time=12, start_time=2, response_time=2, completion_time=12):
        self.pid = pid
        self.arrival_time = arrival_time
        self.burst_time = burst_time
        self._process_ready_queue_id = _process_ready_queue_id
        self.category = category
        self.priority = priority
        self.remaining_time = remaining_time
        self.wait_time = wait_time
        self.turnaround_time = turnaround_time
        self.start_time = start_time
        self.response_time = response_time
        self.completion_time = completion_time

processes = [
Process(pid=0, arrival_time=0, burst_time=8, _process_ready_queue_id=0, category=None, priority=0, remaining_time=0, wait_time=0, turnaround_time=12, start_time=2, response_time=2, completion_time=12),

Process(pid=1, arrival_time=7, burst_time=1, _process_ready_queue_id=0, category=None, priority=0, remaining_time=0, wait_time=5, turnaround_time=10, start_time=14, response_time=7, completion_time=17),

Process(pid=2, arrival_time=20, burst_time=11, _process_ready_queue_id=0, category=None, priority=0, remaining_time=0, wait_time=5, turnaround_time=22, start_time=29, response_time=9, completion_time=42), 

Process(pid=3, arrival_time=21, burst_time=1, _process_ready_queue_id=0, category=None, priority=0, remaining_time=0, wait_time=1, turnaround_time=6, start_time=24, response_time=3, completion_time=27)
]


input_quantum_time: float = 3
input_cs_time: float = 1

algo = "FCFS"
# algo = "SPN"
# algo = "HRRN"
# algo = "Round-Robin"
# algo = "SRTF"










# (processes, font, -4, 0.1, 1.1, 2.1, input_quantum_time, input_cs_time, algo)
def blackboard_dynamic_input_table(processes, font, base_y, at_x_cordinates, bt_x_cordinates, p_x_cordinates, input_quantum_time, input_cs_time, algo):

    # ------------------------------------------------------------------------
    # determining the host collection name
    collection_name = "dynamic input table"

    # If collection exists, get it
    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
    # if not, make it
    else:
        collection = bpy.data.collections.new(collection_name)

    # putting the collection inside the main dynamic collection
    parent_col = bpy.data.collections["Dynamic"]
    child_col = bpy.data.collections["dynamic input table"]

    # Check membership by name or reference
    if parent_col.children.get(child_col.name) is None:
        parent_col.children.link(child_col)
    # ------------------------------------------------------------------------



    # creating the input_quantum_time and input_cs_time and algorithm texts:
    # -------------------------------------------------------------------------------------------------------
    quantum_text = f"{input_quantum_time}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=quantum_text, type='FONT')
    font_curve.body = quantum_text
    font_curve.font = font

    # Create object using the curve data
    quantum_obj = bpy.data.objects.new(name=quantum_text, object_data=font_curve)

    # Link object to the specified collection
    collection.objects.link(quantum_obj)

    # Set transforms (location, rotation, scale)
    quantum_obj.location = (10, 0, 0)    # location (in meters)
    quantum_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    quantum_obj.scale = (1, 1, 1)    # scale

    # ---------------------------------------------------
    context_switch_text = f"{input_cs_time}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=context_switch_text, type='FONT')
    font_curve.body = context_switch_text
    font_curve.font = font

    # Create object using the curve data
    context_switch_obj = bpy.data.objects.new(name=context_switch_text, object_data=font_curve)

    # Link object to the specified collection
    collection.objects.link(context_switch_obj)

    # Set transforms (location, rotation, scale)
    context_switch_obj.location = (15, 0, 0)    # location (in meters)
    context_switch_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    context_switch_obj.scale = (1, 1, 1)    # scale

    # ---------------------------------------------------
    algo_text = f"{algo}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=algo_text, type='FONT')
    font_curve.body = algo_text
    font_curve.font = font

    # Create object using the curve data
    algo_obj = bpy.data.objects.new(name=algo_text, object_data=font_curve)

    # Link object to the specified collection
    collection.objects.link(algo_obj)

    # Set transforms (location, rotation, scale)
    algo_obj.location = (3, 0, 0)    # location (in meters)
    algo_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    algo_obj.scale = (1, 1, 1)    # scale

    # -------------------------------------------------------------------------------------------------------



    # creating the p_i text objects
    y_cordinate = base_y
    for p in processes:

        text_content = f"p{p.pid}"    # numbers the p's based on their index which is the same as pid

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to the specified collection
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (p_x_cordinates, y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate += 0.5


    # creating the at_i text objects
    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.arrival_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (at_x_cordinates, y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate += 0.5


    # creating the bt_i text objects
    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.burst_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (bt_x_cordinates, y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate += 0.5



    # assigning materials:
    # ------------------------------------------------------------------------------
    collection_name = "dynamic input table"
    material_name  = "Chalk Text White"

    # --- Get collection ---
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        raise ValueError(f"Collection '{collection_name}' not found")

    # --- Get material ---
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise ValueError(f"Material '{material_name}' not found")

    # --- Apply to all objects in collection ---
    for obj in coll.objects:

        # Only objects that support materials
        if not hasattr(obj.data, "materials"):
            continue

        # Clear existing materials
        obj.data.materials.clear()

        # Assign the material
        obj.data.materials.append(mat)
    # ------------------------------------------------------------------------------






# (processes, font, -7, x_cordinates_list_sim_results)
def blackboard_dynamic_simulation_result(processes, font, base_y, x_cordinates_list_sim_results):

    # ------------------------------------------------------------------------
    # determining the host collection name
    collection_name = "dynamic simulation result"

    # If collection exists, get it
    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
    # if not, make it
    else:
        collection = bpy.data.collections.new(collection_name)

    # putting the collection inside the main dynamic collection
    parent_col = bpy.data.collections["Dynamic"]
    child_col = bpy.data.collections["dynamic simulation result"]

    # Check membership by name or reference
    if parent_col.children.get(child_col.name) is None:
        parent_col.children.link(child_col)
    # ------------------------------------------------------------------------




    # creating the pid text objects ------------------------------------------------------------------------------------
    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.pid}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to the specified collection
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[0], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5



    # creating the AT text objects ------------------------------------------------------------------------------------
    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.arrival_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[1], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5



    # creating the BT text objects ------------------------------------------------------------------------------------
    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.burst_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[2], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5



    # creating the CT text objects ------------------------------------------------------------------------------------
    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.completion_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[3], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5

    

    # creating the TT text objects ------------------------------------------------------------------------------------

    # calculating the AVG TT ---------------
    all_TT = 0
    for p in processes:
        all_TT += p.turnaround_time
    avg_TT = all_TT / len(processes)
    # --------------------------------------

    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.turnaround_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[4], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5


    # printing the AVG TT ---------------
    y_cordinate = base_y

    text_content = f"{avg_TT}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=text_content, type='FONT')
    font_curve.body = text_content
    font_curve.font = font

    # Create object using the curve data
    text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

    # Link object to scene
    collection.objects.link(text_obj)

    # Set transforms (location, rotation, scale)
    text_obj.location = (x_cordinates_list_sim_results[4], y_cordinate - 4, 0)    # location (in meters)
    text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    text_obj.scale = (0.5, 0.5, 0.5)    # scale

    # --------------------------------------
    


    # creating the WT text objects ------------------------------------------------------------------------------------

    # calculating the AVG WT ---------------
    all_WT = 0
    for p in processes:
        all_WT += p.wait_time
    avg_WT = all_WT / len(processes)
    # --------------------------------------

    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.wait_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[5], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5


    # printing the AVG WT ---------------
    y_cordinate = base_y

    text_content = f"{avg_WT}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=text_content, type='FONT')
    font_curve.body = text_content
    font_curve.font = font

    # Create object using the curve data
    text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

    # Link object to scene
    collection.objects.link(text_obj)

    # Set transforms (location, rotation, scale)
    text_obj.location = (x_cordinates_list_sim_results[5], y_cordinate - 4, 0)    # location (in meters)
    text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    text_obj.scale = (0.5, 0.5, 0.5)    # scale

    # --------------------------------------

    

    # creating the RT text objects ------------------------------------------------------------------------------------

    # calculating the AVG RT ---------------
    all_RT = 0
    for p in processes:
        all_RT += p.response_time
    avg_RT = all_RT / len(processes)
    # --------------------------------------

    y_cordinate = base_y
    for p in processes:

        text_content = f"{p.response_time}"

        # Create font curve data
        font_curve = bpy.data.curves.new(name=text_content, type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

        # Link object to scene
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (x_cordinates_list_sim_results[6], y_cordinate, 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale

        # incrementing y
        y_cordinate -= 0.5


    # printing the AVG RT ---------------
    y_cordinate = base_y

    text_content = f"{avg_RT}"

    # Create font curve data
    font_curve = bpy.data.curves.new(name=text_content, type='FONT')
    font_curve.body = text_content
    font_curve.font = font

    # Create object using the curve data
    text_obj = bpy.data.objects.new(name=text_content, object_data=font_curve)

    # Link object to scene
    collection.objects.link(text_obj)

    # Set transforms (location, rotation, scale)
    text_obj.location = (x_cordinates_list_sim_results[6], y_cordinate - 4, 0)    # location (in meters)
    text_obj.rotation_euler = tuple(map(math.radians, (0, 0, 0)))    # rotation (in degrees)
    text_obj.scale = (0.5, 0.5, 0.5)    # scale

    # --------------------------------------



    # assigning materials ---------------------------------------------------------------------------------------------
    collection_name = "dynamic simulation result"
    material_name  = "Chalk Text White"

    # --- Get collection ---
    coll = bpy.data.collections.get(collection_name)
    if coll is None:
        raise ValueError(f"Collection '{collection_name}' not found")

    # --- Get material ---
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise ValueError(f"Material '{material_name}' not found")

    # --- Apply to all objects in collection ---
    for obj in coll.objects:

        # Only objects that support materials
        if not hasattr(obj.data, "materials"):
            continue

        # Clear existing materials
        obj.data.materials.clear()

        # Assign the material
        obj.data.materials.append(mat)
    # -----------------------------------------------------------------------------------------------------------------






# (gantt, font, 3, 20, -4)
def blackboard_dynamic_gantt_chart(gantt, font, x_min, x_max, base_y):

    # ------------------------------------------------------------------------
    # determining the host collection name
    collection_name = "dynamic gantt chart"

    # If collection exists, get it
    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
    # if not, make it
    else:
        collection = bpy.data.collections.new(collection_name)

    # putting the collection inside the main dynamic collection
    parent_col = bpy.data.collections["Dynamic"]
    child_col = bpy.data.collections["dynamic gantt chart"]

    # Check membership by name or reference
    if parent_col.children.get(child_col.name) is None:
        parent_col.children.link(child_col)
    # ------------------------------------------------------------------------


    
    # Get time range from gantt
    gantt_min = 0
    gantt_max = gantt[-1][1]

    # Define Blender space range
    axis_start = x_min
    axis_end = x_max

    # Compute scale factor
    scale = (axis_end - axis_start) / (gantt_max - gantt_min)

    # Build scaled_gantt
    scaled_gantt = []

    for start, end, pid, event in gantt:
        scaled_start = axis_start + (start - gantt_min) * scale
        scaled_end   = axis_start + (end   - gantt_min) * scale

        scaled_gantt.append( (scaled_start, scaled_end, pid, event) )



    for log in scaled_gantt:

        base_y_cordinate = base_y
        y_shift = (log[2])*(0.5)

        length = log[1] - log[0]


        if log[3] == 'PROCESS_ARRIVAL':
            # Get the object by name
            original = bpy.data.objects["Arrival Mark"]

            # Duplicate object
            duplicated_object = original.copy()

            # copy the object mesh data
            duplicated_object.data = original.data.copy()

            # Link duplicate to the scene collection
            collection.objects.link(duplicated_object)

            # Set location
            duplicated_object.location = (log[0], base_y_cordinate + y_shift, 0)    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~!


        elif log[3] == 'CS_LOAD':
            # Get the object by name
            original = bpy.data.objects["Context Switch Load Bar"]

            # Duplicate object
            duplicated_object = original.copy()

            # copy the object mesh data
            duplicated_object.data = original.data.copy()

            # Link duplicate to the scene collection
            collection.objects.link(duplicated_object)

            # Set location
            duplicated_object.location = (log[0], base_y_cordinate + y_shift, 0)    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~!

            # setting the dimension
            duplicated_object.dimensions = (length, 0.5, 0)


        elif log[3] == 'CS_SAVE':
            # Get the object by name
            original = bpy.data.objects["Context Switch Save Bar"]

            # Duplicate object
            duplicated_object = original.copy()

            # copy the object mesh data
            duplicated_object.data = original.data.copy()

            # Link duplicate to the scene collection
            collection.objects.link(duplicated_object)

            # Set location
            duplicated_object.location = (log[0], base_y_cordinate + y_shift, 0)    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~!

            # setting the dimension
            duplicated_object.dimensions = (length, 0.5, 0)


        elif log[3] == 'EXECUTING':
            # Get the object by name
            original = bpy.data.objects["Execution Bar"]

            # Duplicate object
            duplicated_object = original.copy()

            # copy the object mesh data
            duplicated_object.data = original.data.copy()

            # Link duplicate to the scene collection
            collection.objects.link(duplicated_object)

            # Set location
            duplicated_object.location = (log[0], base_y_cordinate + y_shift, 0)    # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~!

            # setting the dimension
            duplicated_object.dimensions = (length, 0.5, 0)



    # printing the axis numbers on the board
    # ------------------------------------------------------------------------
    # getting every point mentioned in the gantt logs
    point_list_gantt = []
    point_list_scaled_gantt = []

    for log in gantt:
        point_list_gantt.append(log[0])
        point_list_gantt.append(log[1])

    for log in scaled_gantt:
        point_list_scaled_gantt.append(log[0])
        point_list_scaled_gantt.append(log[1])

    # removing the duplicated numbers from the list
    point_list_gantt = list(dict.fromkeys(point_list_gantt))
    point_list_scaled_gantt = list(dict.fromkeys(point_list_scaled_gantt))

    # combing the original points and the scaled points into a list
    combined_point_list = []
    for i in range(len(point_list_gantt)):
        combined_point_list.append( [point_list_gantt[i], point_list_scaled_gantt[i]] )




    base_y_cordinate_offset = 1.5    # the distance between the base_y of the gantt and the axis base_y
    for pair in combined_point_list:

        text_content = f"{pair[0]}"    # numbers the p's based on their index which is the same as pid

        # Create font curve data
        font_curve = bpy.data.curves.new(name=f"axis{pair[0]}", type='FONT')
        font_curve.body = text_content
        font_curve.font = font

        # Create object using the curve data
        text_obj = bpy.data.objects.new(name=f"axis{pair[0]}", object_data=font_curve)

        # Link object to the specified collection
        collection.objects.link(text_obj)

        # Set transforms (location, rotation, scale)
        text_obj.location = (pair[1], base_y_cordinate - (base_y_cordinate_offset), 0)    # location (in meters)
        text_obj.rotation_euler = tuple(map(math.radians, (0, 0, -45)))    # rotation (in degrees)
        text_obj.scale = (0.5, 0.5, 0.5)    # scale


        # --- Get material ------------------------------------------
        material_name  = "Chalk Text White"
        mat = bpy.data.materials.get(material_name)
        if mat is None:
            raise ValueError(f"Material '{material_name}' not found")

        # Assign the material
        text_obj.data.materials.append(mat)
        # --- -------------------------------------------------------





# ...
def blackboard_setup_position():

    # this function return a list of all the objects within a folder tree
    def get_objects_recursively(collection):
        objs = list(collection.objects)
        for child_coll in collection.children:
            objs.extend(get_objects_recursively(child_coll))
        return objs
    
    # -----------------------------------------------------------------------------------------------------------------
    # parenting (parent-keep-tranform) all the objects to the blackboard empty ----------------------------------------------
    COLL_NAME   = "Display"
    PARENT_NAME = "BlackBoard Empty"

    # --- Get collection ---
    coll = bpy.data.collections.get(COLL_NAME)
    if coll is None:
        raise ValueError(f"Collection '{COLL_NAME}' not found")

    # --- Get parent object ---
    parent_obj = bpy.data.objects.get(PARENT_NAME)
    if parent_obj is None:
        raise ValueError(f"Object '{PARENT_NAME}' not found")

    # --- Parent everything in collection (recursively) ---
    for obj in get_objects_recursively(coll):

        # Skip the parent itself
        if obj == parent_obj:
            continue

        # Set parent
        obj.parent = parent_obj

        # Keep world transform (bpy equivalent of Ctrl+P → Keep Transform)
        obj.matrix_parent_inverse = parent_obj.matrix_world.inverted()

    # -----------------------------------------------------------------------------------------------------------------
    # moving the controller empty to position:

    # get the object
    obj = bpy.data.objects["BlackBoard Empty"]

    # making sure the rotation mode is euler xyz
    obj.rotation_mode = 'XYZ'   # Euler XYZ

    # change the location
    obj.location = (-10.2, 20.2, 16) # ((sets)) the location
    obj.rotation_euler.x = math.radians(90) # ((changes)) the rotation

    # obj.rotation_euler = tuple(map(math.radians, (0, 0, 0))) # ((sets)) the rotaion



def blackboard_reset():

    # this function returns a list of all the objects within a folder tree
    def get_objects_recursively(collection):
        objs = list(collection.objects)
        for child_coll in collection.children:
            objs.extend(get_objects_recursively(child_coll))
        return objs
    

    # -----------------------------------------------------------------------------------------------------------------
    col_name   = "Dynamic"

    # --- Get collection ---
    coll = bpy.data.collections.get(col_name)
    if coll is None:
        raise ValueError(f"Collection '{col_name}' not found")


    # --- delete everything in collection (recursively) ---
    if coll:
        for obj in get_objects_recursively(coll):
            bpy.data.objects.remove(obj, do_unlink=True)
    # -----------------------------------------------------



    # --- Get sub collection -----------------------------
    col_name   = "dynamic input table"

    coll = bpy.data.collections.get(col_name)
    if coll is None:
        raise ValueError(f"Collection '{col_name}' not found")

    # --- delete the collection ---------------------------
    if coll:
        bpy.data.collections.remove(coll)
    # -----------------------------------------------------



    # --- Get sub collection -----------------------------
    col_name   = "dynamic simulation result"

    coll = bpy.data.collections.get(col_name)
    if coll is None:
        raise ValueError(f"Collection '{col_name}' not found")

    # --- delete the collection ---------------------------
    if coll:
        bpy.data.collections.remove(coll)
    # -----------------------------------------------------



    # --- Get sub collection -----------------------------
    col_name   = "dynamic gantt chart"

    coll = bpy.data.collections.get(col_name)
    if coll is None:
        raise ValueError(f"Collection '{col_name}' not found")

    # --- delete the collection ---------------------------
    if coll:
        bpy.data.collections.remove(coll)
    # -----------------------------------------------------


    # -----------------------------------------------------------------------------------------------------------------

    # moving the controller empty to the initial position:

    # get the object
    obj = bpy.data.objects["BlackBoard Empty"]

    # making sure the rotation mode is euler xyz
    obj.rotation_mode = 'XYZ'   # Euler XYZ

    # change the location
    obj.location = (0, 0, 0) # ((sets)) the location
    # obj.rotation_euler.x = math.radians(-90) # ((changes)) the rotation

    obj.rotation_euler = tuple(map(math.radians, (0, 0, 0))) # ((sets)) the rotaion

    # -----------------------------------------------------------------------------------------------------------------








# (processes, font, -4, 0.1, 1.1, 2.1, input_quantum_time, input_cs_time, algo)
blackboard_dynamic_input_table(processes, font, -4, 0.1, 1.1, 2.1, input_quantum_time, input_cs_time, algo)


# [pid, AT, BT, CT, TT, WT, RT]
x_cordinates_list_sim_results = [0.1, 1.1, 2.1, 3.1, 4.1, 5.1, 6.1]

# (processes, font, -7, x_cordinates_list_sim_results)
blackboard_dynamic_simulation_result(processes, font, -7, x_cordinates_list_sim_results)


# (gantt, font, 3, 20, -4)
blackboard_dynamic_gantt_chart(gantt, font, 3, 20, -4)


blackboard_setup_position()


blackboard_reset()

