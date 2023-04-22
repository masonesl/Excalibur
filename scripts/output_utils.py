class Colors:
    RED    = "\033[0;91m"
    GREEN  = "\033[0;92m"
    BLUE   = "\033[0;94m"
    YELLOW = "\033[0;93m"
    RESET  = "\033[0m"


def error(message):
    print(f"{Colors.RED}{message}{Colors.RESET}")

def success(message):
    print(f"{Colors.GREEN}{message}{Colors.RESET}")

def info(message):
    print(f"{Colors.BLUE}{message}{Colors.BLUE}")

def warn(message):
    print(f"{Colors.YELLOW}{message}{Colors.RESET}")

# EOF