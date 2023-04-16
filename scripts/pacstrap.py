from subprocess import run
# from os         import chdir,getcwd,listdir

import yaml

command_output = []

with open("config.yaml", "r") as config_file:
    options = yaml.safe_load(config_file)

def pacstrap(mountpoint: str="/mnt") -> None:
    command_output.append(["pacstrap", mountpoint, "base", "base-devel"])

