class Colors:
    RED    = "\033[0;91m"
    GREEN  = "\033[0;92m"
    BLUE   = "\033[0;94m"
    YELLOW = "\033[0;93m"
    RESET  = "\033[0m"


def error(message, end="\n"):
    print(f"{Colors.RED}{message}{Colors.RESET}", end=end)

def success(message, end="\n"):
    print(f"{Colors.GREEN}{message}{Colors.RESET}", end=end)

def info(message, end="\n"):
    print(f"{Colors.BLUE}{message}{Colors.RESET}", end=end)

def warn(message, end="\n"):
    print(f"{Colors.YELLOW}{message}{Colors.RESET}", end=end)

# EOF