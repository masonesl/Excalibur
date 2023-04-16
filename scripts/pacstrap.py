import subprocess

# @TODO Add some type of logging

def pacstrap(mountpoint: str="/mnt") -> list:

    return [subprocess.run(
        ["pacstrap", mountpoint, "base", "base-devel"],
        capture_output=True)]

# EOF