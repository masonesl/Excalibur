import subprocess
# import logging
import os

from yaml import safe_load


ROOT_MOUNTPOINT = "mnt"

program_output = []


with open("config.yaml", "r") as config_file:
    config_options = safe_load(config_file)


PARTITION_DISKS   = False
FORMAT_PARTITIONS = False
PACSTRAP          = False
INSTALL_PACKAGES  = False
CONFIGURE_CLOCK   = False
CONFIGURE_LOCALES = False
CONFIGURE_USERS   = False


def main():
    # Make sure that the mountpoint directory exists and create it if is doesn't
    if not os.path.exists(ROOT_MOUNTPOINT):
        os.mkdir(ROOT_MOUNTPOINT)
    

    
if __name__ == "__main__":
    main()