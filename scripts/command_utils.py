from subprocess import Popen, PIPE
from shlex      import split as shsplit
from enum       import Enum
from typing     import Self, Union, TypedDict

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

class PipeOpts(Enum):
    STDOUT = 4
    STDERR = 2
    STDIN  = 1

    def __and__(self, other: int) -> int:
        return self.value.real & other

    def __or__(self, other: Self) -> int:
        return self.value.real | other.value.real

class PipeOptsDict(TypedDict):
    stdout: Union[int, None]
    stderr: Union[int, None]
    stdin:  Union[int, None]

#------------------------------------------------------------------------------

def execute(
    command       : str,
    pipe_mode     : Union[int, PipeOpts] = PipeOpts.STDOUT,
    dry_run       : bool = False,
    wait_for_proc : bool = True,
    print_errors  : bool = True,
    \
) -> Popen | tuple[bytes, bytes] | None:
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

    std: PipeOptsDict = {
            "stdout" : None,
            "stderr" : None,
            "stdin"  : None,
        }

    if isinstance(pipe_mode, PipeOpts):
        pipe_mode = pipe_mode.value.real

    for pipe_opt, std_code in zip(PipeOpts, std):
        if pipe_opt & pipe_mode == pipe_opt.value.real:
            std[std_code] = PIPE

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
