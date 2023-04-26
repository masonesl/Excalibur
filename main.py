# import logging
import os
import sys

from getpass import getpass
from yaml    import safe_load

sys.path.append(f"{os.getcwd()}/scripts")

from scripts.pacstrap import pacstrap
from scripts.drive_utils import Drive, RaidArray
from scripts.merge_default import Defaults, fill_defaults
from scripts.chroot import Chroot

import scripts.command_utils as command
import scripts.output_utils  as output


NEWROOT_MOUNTPOINT = "mnt"
DRY_RUN            = True

program_output = []


with open("config.yaml", "r") as config_file:
    config_options = fill_defaults(safe_load(config_file), Defaults.PARENT)


PARTITION_DISKS       = True
ENCRYPT_PARTITIONS    = True
FORMAT_PARTITIONS     = True
SETUP_RAID_ARRAYS     = True
MOUNT_FILESYSTEMS     = True
PACSTRAP              = False
  
CHROOT                = True
CONFIGURE_CLOCK       = False
CONFIGURE_LOCALES     = False
CONFIGURE_HOSTS       = False
CONFIGURE_HOSTNAME    = False
CONFIGURE_USERS       = False
CONFIGURE_CRYPT       = True
CONFIGURE_EARLY_CRYPT = False
CONFIGURE_RAID        = False
CONFIGURE_INITRAMFS   = False


def sort_by_mountpoint(partition):
    """
    Return -1 if partition does not have a mountpoint

    Return 0 if mountpoint is / to ensure that it is mounted before anything else

    Return the length of of the mountpoint separated by / to ensure
    that shorter paths will be mounted first
    """
    if not partition[1].mountpoint:
        return -1
    elif partition[1].mountpoint == "/":
        return 0
    elif partition[1].filesystem == "swap":
        return -1
    else:
        return len(partition[1].mountpoint.split("/"))


def get_password(message: str, repeat_message: str):
    passwords_match = False
    while not passwords_match:
        password = getpass(f"{message}: ")
        if getpass(f"{repeat_message}: ") == password:
            passwords_match = True
        else:
            print("Passwords do not match.")

    return password


def main():
    # Make sure that the mountpoint directory exists and create it if is doesn't
    if not os.path.exists(NEWROOT_MOUNTPOINT):
        os.mkdir(NEWROOT_MOUNTPOINT)
    
    if PARTITION_DISKS:
        output.info(": Partitioning drives")

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
                                            uid=uid,
                                            dry_run=DRY_RUN)

                devices[uid] = drives[drive][uid]

    if SETUP_RAID_ARRAYS:
        output.info(": Creating RAID arrays")

        raid_devices = {}

        for uid in config_options["raid"]:
            raid_config = config_options["raid"][uid]
            raid_devices = []

            for raid_device_uid in raid_config["devices"]:
                raid_devices.append(devices[raid_device_uid])
            
            devices[uid] = RaidArray(devices=raid_devices,
                                     array_name=raid_config["array-name"],
                                     level=raid_config["level"],
                                     dry_run=DRY_RUN)

            raid_devices[uid] = devices[uid]

    if ENCRYPT_PARTITIONS:
        output.info(": Encrypting partitions")

        late_crypt_devices = {}
        early_crypt_device = None

        for uid in config_options["crypt"]:
            crypt_config = config_options["crypt"][uid]

            password = get_password(f"Set encryption password for {devices[uid].partition_label}",
                                    f"Repeat password for {devices[uid].partition_label}")

            devices[uid].encrypt_partition(password, crypt_config["crypt-label"])

            if "load-early" in crypt_config and crypt_config["load-early"]:
                early_crypt_device = devices[uid]
            else:
                late_crypt_devices[uid] = devices[uid]

    if FORMAT_PARTITIONS:
        output.info(": Creating filesystems")

        for uid in config_options["filesystems"]:
            filesystem_config = fill_defaults(config_options["filesystems"][uid],
                                              Defaults.FILESYSTEM)

            devices[uid].new_filesystem(filesystem_config["filesystem"],
                                        filesystem_config["label"],
                                        filesystem_config["mountpoint"])

        sorted_devices = dict(sorted(devices.items(), key=sort_by_mountpoint))

    if MOUNT_FILESYSTEMS:
        output.info(": Mounting filesystems")

        for uid in sorted_devices:
            devices[uid].mount_filesystem(f"/mnt{devices[uid].mountpoint}")

    if PACSTRAP:
        output.info(": Running pacstrap")

        pacstrap(dry_run=DRY_RUN)

    if CHROOT:
        command.execute("./mnt/etc/reset.sh")
        with Chroot(target_mountpoint=NEWROOT_MOUNTPOINT, dry_run=DRY_RUN) as chroot_env:
            if CONFIGURE_CLOCK:
                output.info(": Configuring clock")

                clock_config = fill_defaults(config_options["clock"],
                                             Defaults.CLOCK)

                chroot_env.configure_clock(clock_config["timezone"],
                                           clock_config["hardware-utc"],
                                           clock_config["enable-ntp"])

            if CONFIGURE_LOCALES:
                output.info(": Configuring locales")

                locale_config = fill_defaults(config_options["locales"],
                                              Defaults.LOCALES)

                chroot_env.configure_locales(locale_config["locale-gen"],
                                             locale_config["locale-conf"])

            if CONFIGURE_HOSTS:
                output.info(": Configuring hosts")

                chroot_env.configure_hosts()
            
            if CONFIGURE_HOSTNAME:
                output.info(": Setting hostname")

                chroot_env.set_hostname(config_options["hostname"])

            if CONFIGURE_USERS:
                output.info(": Configuring users")

                root_password = get_password("Set password for root",
                                             "Repeat password for root")

                for user in config_options["users"]:
                    config_options["users"][user]["password"] = get_password(
                        f"Set password for {user}",
                        f"Repeat password for {user}"
                    )

                chroot_env.configure_users(root_password, config_options["users"])

            if CONFIGURE_CRYPT:
                if CONFIGURE_EARLY_CRYPT:
                    chroot_env.configure_early_crypt(devices["swap"])
            
            if CONFIGURE_RAID:
                chroot_env.configure_raid(devices["root"])
        
    
if __name__ == "__main__":
    main()

# EOF