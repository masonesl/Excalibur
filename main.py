import subprocess
# import logging
import os

from yaml import safe_load

from scripts.pacstrap import pacstrap
from scripts.drive_utils import Drive
from scripts.merge_default import Defaults, merge

ROOT_MOUNTPOINT = "mnt"

program_output = []


with open("config.yaml", "r") as config_file:
    config_options = safe_load(config_file)


PARTITION_DISKS   = True
FORMAT_PARTITIONS = True
PACSTRAP          = False
INSTALL_PACKAGES  = False
CONFIGURE_CLOCK   = False
CONFIGURE_LOCALES = False
CONFIGURE_USERS   = False

def main():
    # Make sure that the mountpoint directory exists and create it if is doesn't
    if not os.path.exists(ROOT_MOUNTPOINT):
        os.mkdir(ROOT_MOUNTPOINT)
    
    if PARTITION_DISKS:
        drives = {}
        devices = {}

        for drive in config_options["drives"]:
            drive_config = merge(config_options["drives"][drive],
                                 Defaults.DRIVE)

            device_path = drive_config["device-path"]
            gpt         = drive_config["gpt"]

            drives[drive] = Drive(device_path=device_path,
                                  gpt=gpt)

            for uid in drive_config["partitions"]:
                partition_config = merge(drive_config["partitions"][uid],
                                         Defaults.PARTITION)

                drives[drive].new_partition(partition_size=partition_config["size"],
                                            type_code=partition_config["type-code"],
                                            partition_label=partition_config["partition-label"],
                                            uid=uid)
                devices[uid] = drives[drive][uid]

        print(devices)

    if FORMAT_PARTITIONS:
        for uid in config_options["filesystems"]:
            filesystem_config = config_options["filesystems"][uid]

            devices[uid].new_filesystem(filesystem_config["filesystem"],
                                         filesystem_config["label"])

    if PACSTRAP:
        program_output.append(pacstrap(ROOT_MOUNTPOINT))
    
    
if __name__ == "__main__":
    main()