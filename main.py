import os
import sys
import pickle
import argparse

from getpass import getpass
from yaml    import safe_load

sys.path.append(f"{os.getcwd()}/scripts")

from scripts.pacstrap      import pacstrap
from scripts.drive_utils   import Drive, RaidArray
from scripts.config_utils import Defaults, fill_defaults
from scripts.chroot        import Chroot

import scripts.command_utils as cmd
import scripts.output_utils  as output

#------------------------------------------------------------------------------
# These are mainly used for testing

NEWROOT_MOUNTPOINT = "mnt"
DRY_RUN            = True

#------------------------------------------------------------------------------
# Load the config file and fill unspecified information with defaults

with open("config.yaml", "r") as config_file:
    config_options = fill_defaults(safe_load(config_file), Defaults.PARENT)

#------------------------------------------------------------------------------
# Parse arguments

parser = argparse.ArgumentParser(
    prog="excalibur",
    description="Config file based Arch Linux installer"
)

parser.add_argument("--zap-all", "-Z",
                    help="Completely wipe all drives specified in config",
                    dest="ZAP",
                    action="store_true")

subparsers = parser.add_subparsers(dest="subcommand")

run_parser = subparsers.add_parser("run")

args = parser.parse_args()
print(args)

#------------------------------------------------------------------------------

PARTITION_DISKS       = True
ENCRYPT_PARTITIONS    = True
FORMAT_PARTITIONS     = True
SETUP_RAID_ARRAYS     = True
MOUNT_FILESYSTEMS     = True
PACSTRAP              = False
  
CHROOT                = True
CONFIGURE_CLOCK       = True
CONFIGURE_LOCALES     = True
CONFIGURE_HOSTS       = True
CONFIGURE_HOSTNAME    = True
CONFIGURE_USERS       = True
CONFIGURE_CRYPT       = True
CONFIGURE_EARLY_CRYPT = True
CONFIGURE_LATE_CRYPT  = True
CONFIGURE_RAID        = True
CONFIGURE_INITRAMFS   = True

#------------------------------------------------------------------------------
# This function will be used as a key for sorting by mountpoint length to ensure
# that filesystems are mounted in the correct order.
# ie. /home should be mounted before /home/bob

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

#------------------------------------------------------------------------------

def get_password(message: str, repeat_message: str):
    passwords_match = False
    while not passwords_match:
        password = getpass(f"{message}: ")
        if getpass(f"{repeat_message}: ") == password:
            passwords_match = True
        else:
            print("Passwords do not match.")

    return password

#------------------------------------------------------------------------------

def zap_drives():
    output.status("Preparing drives to be wiped...")

    output.substatus("Stopping RAID arrays...")
    cmd.execute("mdadm --stop --scan", dry_run=DRY_RUN)

    output.substatus("Zeroing RAID superblocks...")
    for device in os.listdir("/dev/"):
        for drive in config_options["drives"].values():
            if device.startswith(drive["device-path"]):
                if dev_type := (cmd.execute(f"blkid -s TYPE -o value /dev/{device}", 4)[0].decode().strip() == "linux_raid_member"):
                    cmd.execute(f"mdadm --zero-superblock /dev/{device}", dry_run=DRY_RUN)
    
    output.status("Wiping drives...")
    for drive in config_options["drives"].values():
        output.substatus(f"Wiping device {drive['device-path']}...")
        cmd.execute(f"sgdisk -Z {drive['device-path']}", dry_run=DRY_RUN)

#------------------------------------------------------------------------------
# Password collection functions -----------------------------------------------
#------------------------------------------------------------------------------

def get_encrypt_passwords():
    for encrypted_device in config_options["crypt"]:
        if DRY_RUN:
            config_options["crypt"][encrypted_device]["password"] = "abc123"

        else:
            config_options["crypt"][encrypted_device]["password"] = get_password(
                f"Set encrypt password for {encrypted_device}",
                f"Repeat password for {encrypted_device}"
            )

#------------------------------------------------------------------------------

def get_user_passwords():
    global root_password

    if DRY_RUN:
        root_password = "abc123"
    else:
        root_password = get_password("Set password for root", "Repeat password for root")

    for user in config_options["users"]:
        if DRY_RUN:
            config_options["users"][user]["password"] = "abc123"
        else:
            config_options["users"][user]["password"] = get_password(
                f"Set password for {user}",
                f"Repeat password for {user}"
            )

#------------------------------------------------------------------------------

def partition_drives():
    # Dictionary for physical devices
    global drives
    # Dictionary for formattable devices (ie. partitions, RAID arrays)
    global devices

    drives_config = config_options["drives"]

    output.warn("The following partitions will be created")
    output.warn("Make sure this is what you want as these devices will likely be wiped")
    for drive in drives_config:
        output.warn(f"\t- {drive}")
        for partition in drives_config[drive]["partitions"]:
            output.warn(f"\t\t- {partition}")

    print()
    if (i := output.get_input("Are you sure you would like to continue? (N/y)").lower()) == "n" or i == "":
        exit(1)

    output.info("Continuing...")

    output.status("Partitioning drives...")

    drives = {}
    devices = {}

    for drive in config_options["drives"]:
        output.substatus(f"Partitioning drive '{drive}'...")

        drive_config = fill_defaults(config_options["drives"][drive],
                                        Defaults.DRIVE)

        device_path = drive_config["device-path"]
        gpt         = drive_config["gpt"]

        drives[drive] = Drive(device_path=device_path,
                                gpt=gpt)

        for uid in drive_config["partitions"]:
            output.substatus(f"Creating partition '{uid}'...", 2)

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
        
        output.success(f"'{drive}' has been successfully partitioned!", 1)

#------------------------------------------------------------------------------

def main():
    if args.ZAP:
        zap_drives()
        exit()

    # Make sure that the mountpoint directory exists and create it if is doesn't
    if not os.path.exists(NEWROOT_MOUNTPOINT):
        os.mkdir(NEWROOT_MOUNTPOINT)
    
    #--------------------------------------------------------------------------
    # Get all passwords at the beginning

    # Set all passwords for encrypted devices that should be don't use keyfiles
    if ENCRYPT_PARTITIONS:
        get_encrypt_passwords()

    # Set all user passowrds including root
    if CONFIGURE_USERS:
        get_user_passwords()

    #--------------------------------------------------------------------------

    # Create all specified partitions on the physical drives
    if PARTITION_DISKS:
        partition_drives()

    #--------------------------------------------------------------------------

    if SETUP_RAID_ARRAYS:
        output.status("Creating RAID arrays...")

        raid_devices = []

        for uid in config_options["raid"]:
            output.substatus(f"Creating array '{uid}'...")

            raid_config = config_options["raid"][uid]
            raid_array_devices = []

            for raid_device_uid in raid_config["devices"]:
                output.substatus(f"Adding device '{raid_device_uid}' to array '{uid}'", 2)
                raid_array_devices.append(devices[raid_device_uid])
            
            devices[uid] = RaidArray(devices=raid_array_devices,
                                     array_name=raid_config["array-name"],
                                     level=raid_config["level"],
                                     dry_run=DRY_RUN)

            raid_devices.append(devices[uid])

            output.success(f"RAID array '{uid}' has been successfully created!", 1)

    #--------------------------------------------------------------------------

    if ENCRYPT_PARTITIONS:
        output.status("Encrypting devices...")

        late_crypt_devices = []
        early_crypt_device = None

        for uid in config_options["crypt"]:
            output.substatus(f"Encrypting device '{uid}'...")

            crypt_config = fill_defaults(config_options["crypt"][uid], Defaults.CRYPT)

            devices[uid].encrypt_partition(crypt_config["password"],
                                           crypt_config["crypt-label"],
                                           crypt_config["generate-keyfile"])

            if "load-early" in crypt_config and crypt_config["load-early"]:
                if early_crypt_device:
                    output.warn(f"Cannot set '{devices[uid].partition_label}' to load early.")
                    output.warn(f"'{early_crypt_device.partition_label}' is already set to load early.")
                    exit(1)
                else:
                    early_crypt_device = devices[uid]
                    output.info(f"Device '{uid}' set to decrypt in early userspace", 1)
            else:
                late_crypt_devices.append(devices[uid])

            output.success(f"Device '{uid}' has been successfully encrypted!", 1)

    #--------------------------------------------------------------------------

    if FORMAT_PARTITIONS:
        output.status("Creating filesystems...")

        for uid in config_options["filesystems"]:
            filesystem_config = fill_defaults(config_options["filesystems"][uid],
                                              Defaults.FILESYSTEM)

            output.substatus(f"Creating filesystem on '{uid}'...")

            devices[uid].new_filesystem(filesystem_config["filesystem"],
                                        filesystem_config["label"],
                                        filesystem_config["mountpoint"])

            output.success(f"Device '{uid}' has been successfully formatted!", 1)

        sorted_devices = dict(sorted(devices.items(), key=sort_by_mountpoint))

    #--------------------------------------------------------------------------

    if MOUNT_FILESYSTEMS:
        output.status("Mounting filesystems...")

        for uid in sorted_devices:
            devices[uid].mount_filesystem(f"/mnt{devices[uid].mountpoint}")

        output.status("Filesystems successfully mounted!")

    #--------------------------------------------------------------------------

    if PACSTRAP:
        output.status("Running pacstrap...")

        pacstrap(dry_run=DRY_RUN)

        output.status("Pacstrap completed successfully!")

    #--------------------------------------------------------------------------

    if CHROOT:
        # Reset the temporary test chroot environment
        # Only contains a few files for the chroot class to modify
        if DRY_RUN:
            cmd.execute("./mnt/etc/reset.sh")

        with Chroot(target_mountpoint=NEWROOT_MOUNTPOINT, dry_run=DRY_RUN) as chroot_env:
            output.status("Chroot envrionment created")

            if CONFIGURE_CLOCK:
                output.substatus("Configuring clock...")

                clock_config = fill_defaults(config_options["clock"], Defaults.CLOCK)

                chroot_env.configure_clock(clock_config["timezone"],
                                           clock_config["hardware-utc"],
                                           clock_config["enable-ntp"])

            #------------------------------------------------------------------

            if CONFIGURE_LOCALES:
                output.substatus("Configuring Locales...")

                locale_config = fill_defaults(config_options["locales"], Defaults.LOCALES)

                chroot_env.configure_locales(locale_config["locale-gen"],
                                             locale_config["locale-conf"])

            #------------------------------------------------------------------

            if CONFIGURE_HOSTS:
                output.info(": Configuring hosts")

                chroot_env.configure_hosts()

            #------------------------------------------------------------------
            
            if CONFIGURE_HOSTNAME:
                output.info(": Setting hostname")

                chroot_env.set_hostname(config_options["hostname"])

            #------------------------------------------------------------------

            if CONFIGURE_USERS:
                output.substatus("Configuring users...")

                chroot_env.set_root_password(root_password)

                for user in config_options["users"]:
                    user_config = config_options["users"][user]
                    chroot_env.configure_user(user,
                                              user_config["shell"],
                                              user_config["home"],
                                              user_config["comment"],
                                              user_config["groups"],
                                              user_config["password"])

            #------------------------------------------------------------------

            if CONFIGURE_CRYPT:
                if CONFIGURE_EARLY_CRYPT and early_crypt_device:
                    chroot_env.configure_early_crypt(early_crypt_device)
                if CONFIGURE_LATE_CRYPT:
                    for crypt_device in late_crypt_devices:
                        chroot_env.configure_late_crypt(crypt_device)
            
            if CONFIGURE_RAID:
                chroot_env.configure_raid(devices["root"])
        
#------------------------------------------------------------------------------

if __name__ == "__main__":
    main()

# EOF