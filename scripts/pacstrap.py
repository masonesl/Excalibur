from subprocess import run

command_output = []

def pacstrap(mountpoint: str="/mnt") -> None:
    command_output.append(["pacstrap", mountpoint, "base", "base-devel"])

