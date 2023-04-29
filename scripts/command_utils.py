from subprocess import Popen, PIPE
from shlex      import split as shsplit
from time       import sleep

import output_utils as output


STD_CODES = {
    "stdout" : 4,
    "stderr" : 2,
    "stdin"  : 1
}


def execute(command: str, pipe_mode: int=2, dry_run=False, wait_for_proc=True, print_errors=True):
    if dry_run:
        output.print_command(command)
        sleep(.1)
        return

    std = {
        "stdout" : None,
        "stderr" : None,
        "stdin"  : None
    }

    for std_code in STD_CODES:
        if pipe_mode - STD_CODES[std_code] >= 0:
            std[std_code] = PIPE
            pipe_mode -= STD_CODES[std_code]

    process = Popen(shsplit(command), stdout=std["stdout"],
                                      stderr=std["stderr"],
                                      stdin =std["stdin"])
    
    if not wait_for_proc:
        return process
    
    proc_comm = process.communicate()

    # If there are any errors, print them
    if print_errors and std["stderr"] and process.poll() != 0:
        output.error(f"Command '{command}' failed to execute")
        print(proc_comm[1].decode())

    return proc_comm

# EOF