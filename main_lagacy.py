import time

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
PURPLE = "\033[35m"   # aka MAGENTA
BRIGHT_PURPLE = "\033[95m"
GRAY = "\033[90m"


# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------


class Program:
    def __init__(self, program_name, program_instructions, program_metadata):
        self.program_name = program_name        # (string): Program name
        self.program_instructions = program_instructions        # (list): list of IR instructions
        self.program_size = len(program_instructions)        # (int): program size in KB
        self.program_metadata = program_metadata        # (list): anything user-level (file path, description, tags)

    def update_program_size(self):
        self.program_size = len(self.program_instructions)


class HardDrive:
    def __init__(self, hard_drive_program_list= []):
        self.hard_drive_program_list = hard_drive_program_list    # (list): program objects imported from .json file


# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------


class RAM:
    def __init__(self):
        self.full_space = 4096
        self.allocated_space = 0
        self.remaining_space = self.full_space - self.allocated_space
        self.ram_processes = []   # (list): a list of process objects
        # self.allocations = []   # list of (pid, start, end)

    def update_remaining_space(self):
        self.remaining_space = self.full_space - self.allocated_space


class CPU:
    def __init__(self):
        self.cpu_active_process = None
        self.cpu_timer = None



# New → Ready : Long Term Scheduler
# Ready → Running : Short Term Scheduler

# Running → Ready : Timer interrupt + OS Scheduler

# Running → Waiting : The Running Process triggers it, OS handles it
# Waiting → Ready : Interrupt handler (Part of OS)

# Running → Terminated : Process triggers exit, OS cleans up



def cpu(program_counter):
    global current_time, TICK, TPI, global_LOG, STS_AL, LTS_AL, cpu_0, ready_queue
    # global_LOG.append(f"{GRAY}{current_time} \t def short_term_scheduler({sts_algorithm}) \t Function Called{RESET}")

    cpu_0.cpu_timer = 0

    for instruction in cpu_0.cpu_active_process.process_code[program_counter:]:  # starts iteration from the pc'th index

        if instruction == "exit()":
            # exitting and terminating the prcess
            pass

        # Execution of the instruction:
        # -------------------------------------------------------
        # incrementing the process's pc
        # time.sleep(TPI/1000)  # 20/1000 would be 20 mili-secods
        cpu_0.cpu_active_process.process_pcb.program_counter += 1
        # -------------------------------------------------------

        # Time interrupt:
        # -------------------------------------------------------
        # incrementing the Timer interrupt
        cpu_0.cpu_timer += 1

        # time slice expiration
        if cpu_0.cpu_timer == 10:
            cpu_0.cpu_timer = 0
            break
        # -------------------------------------------------------
        
        
        
        # current_time += TICK



# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------

current_time = 0
global_LOG = []

pID_table = {}

TICK = 1  # (Time Increment scale) for incrementing the general current time
TPI = 20  # (Time Per Instrucion)(in mili-seconds) the amount of time it takes for each cpu instruction to be executed

LTS_AL = ["FCFS", "SJF", "Priority"]
STS_AL = ["FCFS", "SJF", "Priority", "Round-Robin"]
new_queue = []    # list: Processes in "new" state
ready_queue = []    # list: Processes in "ready" state
waiting_queue = []    # list: Processes in "waiting" state
terminated_list = []    # list: Completed processes for stats


class PCB:
    def __init__(self, pID):
        self.pID = pID      # (int)
        self.program_counter = int(0)     # (int)

        self.process_state = "NEW"      # (string): new, ready, running, waiting, terminated
        self.scheduling_info = {"priority": None, "total_cpu_time": None}   # (dictionary): {priority, total_cpu_time, ...}
        self.accounting = {"cpu_time": int(0), "io_time": int(0)}   # (dictionary): { cpu_time, io_time, ... }
        
        # self.registers = {}
        # self.remaining_time = 0


class Process:
    def __init__(self, process_name, process_pcb, process_code, process_metadata):
        self.process_name = process_name        # (string): process name 
        self.process_pcb = process_pcb      # PCB class object
        self.process_code = process_code    # (list): a list of place-holder text that is meant too represent code.
        self.process_metadata = process_metadata        # (List): description, file_path, [tags]
        self.process_arrival_time = None
        self.process_estimated_burst_time = None
        self.process_remaining_burst_time = None
        # self.process_burst_time = None
        # self.process_turnaround_time = None
        # self.process_waiting_time = None
        # self.process_response_time = None


# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------


def hard_drive_program_load(filename):
    global current_time, global_LOG
    global_LOG.append(f"{GRAY}{current_time} \t hard_drive_program_load({filename}) \t Function Called{RESET}")

    def random_instrucion_generator(program_size):
        import random
        instruction_list = []
        list_0_1 = [0, 1]


        for i in range(program_size):

            instruction_as_lst = [0]*16

            for j in range(len(instruction_as_lst)):
                instruction_as_lst[j] = str(random.choice(list_0_1))

            instruction_as_lst.insert(1, " ")
            instruction_as_lst.insert(5, " ")

            instruction_as_str = "".join(instruction_as_lst)

            instruction_list.append(instruction_as_str)

        return instruction_list

    import json

    with open(filename) as f:
        data = json.load(f)

    program_list = []
    for p in data:

        tags = p["metadata"]["tags"]

        metadata_list = [p["metadata"]["path"], p["metadata"]["description"], tags]

        # generaing random instructions to fill the instruction list
        instruction_list = random_instrucion_generator(p["size"])
        # replacing the last insruction with "exit()"
        instruction_list.pop(-1)
        instruction_list.append("exit()")


        created_program = Program(p["name"], instruction_list, metadata_list)
        created_program.update_program_size()

        program_list.append(created_program)


    global_LOG.append(f"{current_time} \t def hard_drive_program_load(filename) \t {len(program_list)} program/programs were succesfully loaded into [ {HardDrive} ] from [ {filename} ]")
    return program_list


def create_process(program):
    global current_time, TICK, global_LOG, pID_table, new_queue
    global_LOG.append(f"{GRAY}{current_time} \t create_process({program}) \t Function Called{RESET}")


    created_process_name = program.program_name    # name
    created_process_code = program.program_instructions    # code
    created_process_metadata = program.program_metadata    # meadata

    # pID creation
    created_pID = (len(pID_table) + 1)
    created_process_pcb = PCB(created_pID)    # pcb


    # Setting initial scheduling info based on program metadata/size
    if "#High_Priority" in created_process_metadata[2]:
        priority = 1
    elif "#Low_Priority" in created_process_metadata[2]:
        priority = 10
    else:
        priority = 5
    
    created_process_pcb.scheduling_info["priority"] = priority
    created_process_pcb.scheduling_info["total_cpu_time"] = program.program_size  # Placeholder: size as estimated CPU time

    # creating the process object
    created_process = Process(created_process_name, created_process_pcb, created_process_code, created_process_metadata)
    
    # assigning pID to process
    pID_table.update( { created_process_pcb.pID : created_process } )

    # Set initial timings
    created_process.process_arrival_time = current_time
    created_process.process_estimated_burst_time = program.program_size
    created_process.process_remaining_burst_time = program.program_size
    
    # assigning to the new_queue
    new_queue.append(created_process)


    current_time += TICK
    global_LOG.append(f"{current_time} \t def create_process({program}) \t program: [ {program} → {program.program_name}, {len(program.program_instructions)}, {program.program_metadata[2]}] \n\t\t became a process: [ {created_process} →  {created_process_name}, {len(created_process_code)}, {created_process_metadata[2]}\n\t \t with pcb: {created_process.process_pcb.pID}, {created_process.process_pcb.process_state}, {created_process.process_pcb.scheduling_info}, {created_process.process_pcb.accounting} ]")

    return created_process


def long_term_scheduler(lts_algorithm):
    global current_time, TICK, global_LOG, Ram, new_queue, ready_queue
    global_LOG.append(f"{GRAY}{current_time} \t def long_term_scheduler({lts_algorithm}) \t Function Called{RESET}")

    if new_queue:

        if (lts_algorithm == "FCFS"):  # (First Come First Served)

            process = new_queue[0]  # FCFS admission
            process_logged = process # declared for logging purpuses only

            process_size = process.process_estimated_burst_time

            if Ram.remaining_space >= process_size:
                
                # changing the process state
                process.process_pcb.process_state = "READY"
                ready_queue.append(process)
                new_queue.pop(0)
                
                # allocating RAM space
                Ram.allocated_space += process_size
                Ram.update_remaining_space()

                # adding the process to the list of processes in the RAM
                Ram.ram_processes.append(process)

                global_LOG.append(f"{current_time} \t def long_term_scheduler({BLUE}{lts_algorithm}{RESET}) \t {GREEN}PROCESS ADMITTED{RESET} \t process selected: {process}, name: {process.process_name}, pID: {process.process_pcb.pID}, size: {len(process.process_code)}")


            else:
                process = None

        elif (lts_algorithm == "SJF"):
            
            # putting all the process size/estimated_burst_time into a list
            size_list = []
            for p in new_queue:
                size_list.append(p.process_estimated_burst_time)

            # finding the index of the smallest/shortest process
            min_index = size_list.index(min(size_list))

            # finding the process based on the index
            process = new_queue[min_index]
            process_logged = process # declared for logging purpuses only


            process_size = process.process_estimated_burst_time

            if Ram.remaining_space >= process_size:
                
                # changing the process state
                process.process_pcb.process_state = "READY"
                ready_queue.append(process)
                new_queue.pop(min_index)

                
                # allocating RAM space
                Ram.allocated_space += process_size
                Ram.update_remaining_space()

                # adding the process to the list of processes in the RAM
                Ram.ram_processes.append(process)
                
                global_LOG.append(f"{current_time} \t def long_term_scheduler({BLUE}{lts_algorithm}{RESET}) \t {GREEN}PROCESS ADMITTED{RESET} \t process selected: {process}, name: {process.process_name}, pID: {process.process_pcb.pId}, size: {len(process.process_code)}")

            else:
                process = None

            # elif (lts_algorithm == "PRIORITY"):
            #     pass

        else:
            global_LOG.append(f"{RED}{current_time} \t def long_term_scheduler({BLUE}{lts_algorithm}{RESET}{RED}) \t ValueError(f'Unknown LT Scheduler algorithm: {lts_algorithm}'){RESET}")
            raise ValueError(f"Unknown LT Scheduler algorithm: {lts_algorithm}")
            

        current_time += TICK
        if process == None:
            global_LOG.append(f"{current_time} \t def long_term_scheduler({BLUE}{lts_algorithm}{RESET}) \t {YELLOW}ADMITION FAILED, Not enough space on RAM{RESET} \t process selected: {process_logged}, name: {process_logged.process_name}, pID: {process_logged.process_pcb.pId}, size: {len(process_logged.process_code)}")
        return process
    
    else:
        global_LOG.append(f"{current_time} \t def long_term_scheduler({BLUE}{lts_algorithm}{RESET}) \t new_queue is empty \t returning {PURPLE}None{RESET}")
        return None


def short_term_scheduler(sts_algorithm):
    global current_time, TICK, global_LOG, STS_AL, cpu_0, ready_queue
    global_LOG.append(f"{GRAY}{current_time} \t def short_term_scheduler({sts_algorithm}) \t Function Called{RESET}")

    # Dispatch based on STS algorithm
    if (cpu_0.cpu_active_process == None) and (sts_algorithm == "FCFS"):
        process = ready_queue[0]  # picking the first process that has entered the list
        
        # dispatching step
        cpu_0.cpu_active_process = process  # loading the process onto the cpu
        cpu_0.cpu_active_process.process_pcb.process_state = "RUNNING"  # changing the process pcb state
        ready_queue.pop(0)  # removing from the ready_queue
        
        current_time += TICK
        global_LOG.append(f"{current_time} \t def short_term_scheduler({BLUE}{sts_algorithm}{RESET}) \t {GREEN}PROCESS SELECTED{RESET} \t process selected: {process}, name: {process.process_name}, pID: {process.process_pcb.pID}, size: {len(process.process_code)}")
        return process

    elif (cpu_0.cpu_active_process == None) and (sts_algorithm == "SJF"):

        # putting all the process size/estimated_burst_time into a list
        size_list = []
        for p in ready_queue:
            size_list.append(p.process_estimated_burst_time)

        # finding the index of the smallest/shortest process
        min_index = size_list.index(min(size_list))

        # finding the process based on the index
        process = ready_queue[min_index]
        
        # dispatching step
        cpu_0.cpu_active_process = process  # loading the process onto the cpu
        cpu_0.cpu_active_process.process_pcb.process_state = "RUNNING"  # changing the process pcb state
        ready_queue.pop(min_index)  # removing from the ready_queue
        
        current_time += TICK
        global_LOG.append(f"{current_time} \t def short_term_scheduler({BLUE}{sts_algorithm}{RESET}) \t {GREEN}PROCESS SELECTED{RESET} \t process selected: {process}, name: {process.process_name}, pID: {process.process_pcb.pID}, size: {len(process.process_code)}")
        return process

    # elif sts_algorithm == "Priority":
    #     pass
    # elif sts_algorithm == "Round-Robin":
    #     pass
    else:
        if sts_algorithm not in STS_AL:
            global_LOG.append(f"{RED}{current_time} \t def short_term_scheduler({BLUE}{sts_algorithm}{RESET}{RED}) \t ValueError(f'Unknown ST Scheduler algorithm: {sts_algorithm}'){RESET}")
            raise ValueError(f"Unknown ST Scheduler algorithm: {sts_algorithm}")
        
        return None


# does the context switch
def dispatcher(process):
    global current_time, TICK, TPI, global_LOG, STS_AL, LTS_AL, cpu_0, ready_queue






    pass


# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------
# ----------------------------------------------------------------------------------------------------


def main():
    HardDrive = HardDrive()
    Ram = RAM()
    cpu_0 = CPU()

    # loading programs into the HardDrive (except the program instructions)
    HardDrive.hard_drive_program_list = hard_drive_program_load("Programs.json")

    # while()



    pass







# ------------------------------------------------------------------
# Test:
print("\n")
print(HardDrive.hard_drive_program_list[2].program_name)
print(HardDrive.hard_drive_program_list[2].program_size)
print(HardDrive.hard_drive_program_list[2].program_instructions)
print("\n \n \n")
# ------------------------------------------------------------------

# Test:
# creating a process out of some program and adding it to the new_queue
p0 = create_process(HardDrive.hard_drive_program_list[2])

# a = new_queue[0]
# print(a.process_name, a.process_pcb.pID, a.process_pcb.process_state)


print(type(p0.process_pcb.scheduling_info))
print(type(p0.process_pcb.accounting))












