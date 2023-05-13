from subprocess import Popen, PIPE
from shlex      import split as shsplit

import output_utils as output

#------------------------------------------------------------------------------

class CommandFailedException(Exception):
    
    def __init__(self, *args: object) -> None:
        super().__init__(*args)

#------------------------------------------------------------------------------

STD_CODES = {
    "stdout" : 4,
    "stderr" : 2,
    "stdin"  : 1
}

#------------------------------------------------------------------------------

def execute(
    command       : str,
    pipe_mode     : int  = 2,
    dry_run       : bool = False,
    wait_for_proc : bool = True,
    print_errors  : bool = True,
    \
) -> Popen | tuple[bytes, bytes]:
    """Execute a command

    Parameters
    ----------
    command : str
        Command to be executed
    pipe_mode : int, optional
        Octal code to specify which streams should be pipes, by default 2
        
            1 corresponds to stdin  \n
            2 corresponds to stderr \n
            4 corresponds to stdout \n
            
    dry_run : bool, optional
        If true, only print the command instead of executing, by default False
    wait_for_proc : bool, optional
        If true, wait for the process to finish before returning, by default True
    print_errors : bool, optional
        If true, print errors if the return code is not 0, by default True

    Returns
    -------
    tuple[bytes, bytes]
        If wait_for_proc is True, return the result of process.communicate
    Popen
        If wait_for_proc is False, return the process itself

    Raises
    ------
    CommandFailedException
        Raised if the specified command exits with a non-zero return code and the user chooses not to continue
    """
    
    if dry_run:
        output.print_command(command)
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

    process = Popen(
        shsplit(command),
        stdout=std["stdout"],
        stderr=std["stderr"],
        stdin =std["stdin"]
    )
    
    if not wait_for_proc:
        return process
    
    proc_comm = process.communicate()

    # If there are any errors, print them
    if print_errors and std["stderr"] and process.poll() != 0:
        output.error(f"Command '{command}' failed to execute")
        print(proc_comm[1].decode())

        if (i := output.get_input(
            "Would you like to continue? (N/y)"
            ).lower()) == "n" or i == "":
            
            raise CommandFailedException(command)

    return proc_comm

# EOF