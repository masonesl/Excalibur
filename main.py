import subprocess
# import logging
import os

from getpass import getpass
from yaml    import safe_load

from scripts.pacstrap import pacstrap
from scripts.drive_utils import Drive, RaidArray
from scripts.merge_default import Defaults, fill_defaults
from scripts.chroot import Chroot


ROOT_MOUNTPOINT = "mnt"

program_output = []


with open("config.yaml", "r") as config_file:
    config_options = fill_defaults(safe_load(config_file), Defaults.PARENT)


PARTITION_DISKS    = False
ENCRYPT_PARTITIONS = False
FORMAT_PARTITIONS  = False
SETUP_RAID_ARRAYS  = False
MOUNT_FILESYSTEMS  = False
PACSTRAP           = False
CHROOT             = True
CONFIGURE_CLOCK    = True
CONFIGURE_LOCALES  = False
CONFIGURE_HOST     = False
CONFIGURE_USERS    = False

# Default config should be merged with actual config before doing anything else

def sort_by_mountpoint(partition):
    if not partition[1].mountpoint:
        return -1
    elif partition[1].mountpoint == "/":
        return 0
    elif partition[1].filesystem == "swap":
        return -1
    else:
        return len(partition[1].mountpoint.split("/"))

def main():
    # Make sure that the mountpoint directory exists and create it if is doesn't
    if not os.path.exists(ROOT_MOUNTPOINT):
        os.mkdir(ROOT_MOUNTPOINT)
    
    if PARTITION_DISKS:
        drives = {}
        devices = {}

        for drive in config_options["drives"]:
            drive_config = fill_defaults(config_options["drives"][drive],
                                         Defaults.DRIVE)

            device_path = drive_config["device-path"]
            gpt         = drive_config["gpt"]

            drives[drive] = Drive(device_path=device_path,
                                  gpt=gpt)

            for uid in drive_config["partitions"]:
                partition_config = fill_defaults(drive_config["partitions"][uid],
                                                 Defaults.PARTITION)

                drives[drive].new_partition(partition_size=partition_config["size"],
                                            start_sector=partition_config["start-sector"],
                                            end_sector=partition_config["end-sector"],
                                            type_code=partition_config["type-code"],
                                            partition_label=partition_config["partition-label"],
                                            uid=uid)

                devices[uid] = drives[drive][uid]

    if SETUP_RAID_ARRAYS:
        for uid in config_options["raid"]:
            raid_config = config_options["raid"][uid]
            raid_devices = []

            for raid_device_uid in raid_config["devices"]:
                raid_devices.append(devices[raid_device_uid])
            
            devices[uid] = RaidArray(devices=raid_devices,
                                     array_name=raid_config["array-name"],
                                     level=raid_config["level"])

    if ENCRYPT_PARTITIONS:
        for uid in config_options["crypt"]:
            crypt_config = config_options["crypt"][uid]

            passwords_match = False
            while not passwords_match:
                password = getpass(f"Set password for {uid}: ")
                if getpass(f"Repeat password for {uid}: ") == password:
                    passwords_match = True
                else:
                    print("Passwords do not match.")

            devices[uid].encrypt_partition(password, crypt_config["crypt-label"])

    if FORMAT_PARTITIONS:
        for uid in config_options["filesystems"]:
            filesystem_config = fill_defaults(config_options["filesystems"][uid],
                                              Defaults.FILESYSTEM)

            devices[uid].new_filesystem(filesystem_config["filesystem"],
                                        filesystem_config["label"],
                                        filesystem_config["mountpoint"])

        sorted_devices = dict(sorted(devices.items(), key=sort_by_mountpoint))
        print(devices)
        print(sorted_devices)

    if MOUNT_FILESYSTEMS:
        for uid in sorted_devices:
            devices[uid].mount_filesystem(f"/mnt{devices[uid].mountpoint}")

    if PACSTRAP:
        pacstrap()

    if CHROOT:
        with Chroot() as chroot_env:
            if CONFIGURE_CLOCK:
                clock_config = fill_defaults(config_options["clock"],
                                             Defaults.CLOCK)

                chroot_env.configure_clock(clock_config["timezone"],
                                           clock_config["hardware-utc"],
                                           clock_config["enable-ntp"])

            if CONFIGURE_LOCALES:
                locale_config = fill_defaults(config_options["locales"],
                                              Defaults.LOCALES)

                chroot_env.configure_locales(locale_config["locale-gen"],
                                             locale_config["locale-conf"])

            if CONFIGURE_HOST:
                chroot_env.configure_host(config_options["hostname"])
        
    
if __name__ == "__main__":
    main()