class Output:
    ESC     = "\033["
    RESET   = "\033[0m"
 
    NORMAL  = "0;"
    BOLD    = "1;"
 
    DEFAULT = "39m"
    WHITE   = "37m"
    RED     = "91m"
    GREEN   = "92m"
    BLUE    = "94m"
    YELLOW  = "93m"
    MAGENTA = "35m"

    @staticmethod
    def format_output(message, mode=None, color=None):
        if not mode:
            mode = Output.NORMAL
        if not color:
            color = Output.DEFAULT

        return f"{Output.ESC}{mode}{color}{message}{Output.RESET}"

#------------------------------------------------------------------------------

def print_symbol(symbol: str, color: Output):
    print(Output.format_output(symbol, Output.BOLD, color), end=" ")

#------------------------------------------------------------------------------

def error(message):
    print_symbol("<!>", Output.RED)
    print(Output.format_output(message, Output.BOLD))

def success(message, nest_val: int=0):
    print_symbol(f"{''.join([' + ' for i in range(nest_val)])}<:>", Output.GREEN)
    print(Output.format_output(message, Output.BOLD))

def status(message, end="\n"):
    print(Output.format_output("<+>", Output.BOLD, Output.BLUE), end=" ")
    print(Output.format_output(message, Output.BOLD), end=end)

def substatus(message, nest_val: int=1):
    print_symbol(f" +{''.join('  ' for i in range(nest_val))}->", Output.BLUE)
    print(message)

def info(message, nest_val: int=0):
    print_symbol(f"{''.join(['   ' for i in range(nest_val)])}:::", Output.BLUE)
    print(message)

def warn(message, end="\n"):
    print(Output.format_output("<#>", Output.BOLD, Output.YELLOW), end=" ")
    print(Output.format_output(message, Output.BOLD), end=end)

def print_command(command):
    print(Output.format_output("<>> Executing", Output.BOLD, Output.WHITE), end=" ")
    print(command)

def get_input(message):
    print(Output.format_output("<?>", Output.BOLD, Output.MAGENTA), end=" ")
    return input(Output.format_output(message+" ", Output.BOLD))

# EOF