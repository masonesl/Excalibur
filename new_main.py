import os
import sys
import pickle
import argparse

from getpass import getpass

sys.path.append(f"{os.getcwd()}/scripts")

from scripts.pacstrap      import pacstrap
from scripts.drive_utils   import Drive, RaidArray
from scripts.merge_default import Defaults, Config
from scripts.chroot        import Chroot

import scripts.command_utils as cmd
import scripts.output_utils  as output


class Excalibur:

    def __init__(self, parser: argparse.ArgumentParser):
        self.args = self.__parse_args(parser)

        self.config = Config(self.args.CONFIG_FILE_PATH)

        # Exit and print missing options if there are any
        if self.config.missing_required:
            output.error(f"Missing required options in {self.args.CONFIG_FILE_PATH}:\n")
            for option in self.config.missing_required:
                output.error(" >> ".join(option))
            exit(1)

        self.dry_run = self.args.DRY_RUN
        self.target  = self.args.MOUNTPOINT

        # Placeholder root password until it gets set
        # Only should be used when dry running
        self.root_password = "password"

        # Stores physical device information
        self.drives = {}
        # Stores formattable devices like partitions and RAID arrays
        self.devices = {}

        # List of devices to be unlocked in late userspace via /etc/crypttab
        self.late_crypt_devices = []
        # Device to be unlock in early userspace via initrd
        # For now, only one device can be set
        self.early_crypt_device = None

    def __parse_args(self, parser: argparse.ArgumentParser) -> argparse.Namespace:
        parser.add_argument("-Z", "--zap-all",
                            help="Wipe all drives specified in config",
                            dest="ZAP",
                            action="store_true")

        parser.add_argument("-c", "--config",
                            help="Specify which config file to use",
                            dest="CONFIG_FILE_PATH",
                            metavar="file path",
                            action="store",
                            default="config.yaml")

        parser.add_argument("-d", "--dry-run", 
                            help="Print, don't execute commands",
                            dest="DRY_RUN",
                            action="store_true")

        parser.add_argument("-m", "--mountpoint",
                            help="Specify the mountpoint for the new root",
                            dest="MOUNTPOINT",
                            metavar="target",
                            action="store",
                            default="/mnt/excalibur")

        return parser.parse_args()

    #--------------------------------------------------------------------------
    # Static Methods ----------------------------------------------------------
    #--------------------------------------------------------------------------

    @staticmethod
    def sort_by_mountpoint(partition) -> int:
        """To be used as a key for sorting by mountpoint length to ensure
        that filesystems are mounted in the correct order
        ie. /home should be mounted before /home/bob

        Args:
            partition (Formattable): _description_

        Returns:
            int: _description_
        """
        if not partition[1].mountpoint:
            return -1
        elif partition[1].mountpoint == "/":
            return 0
        elif partition[1].filesystem == "swap":
            return -1
        else:
            return len(partition[1].mountpoint.split("/"))

    #--------------------------------------------------------------------------

    @staticmethod
    def get_password(message: str, repeat_message: str) -> str:
        passwords_match = False
        while not passwords_match:
            password = getpass(f"{message}: ")
            if getpass(f"{repeat_message}: ") == password:
                passwords_match = True
            else:
                print("Passwords do not match.")

        return password

    #--------------------------------------------------------------------------
    # Password Collection Methods ---------------------------------------------
    #--------------------------------------------------------------------------

    def collect_user_passwords(self):
        self.root_password = self.get_password("Set password for root",
                                               "Repeat password for root")

        for user in self.config["users"]:
            self.config["users"][user]["password"] = self.get_password(
                f"Set password for {user}",
                f"Repeat password for {user}"
            )

    #--------------------------------------------------------------------------

    def collect_crypt_passwords(self):
        for crypt_device in self.config["crypt"]:
            self.config["crypt"][crypt_device]["password"] = self.get_password(
                f"Set encrypt password for {crypt_device}",
                f"Repeat password for {crypt_device}"
            )

    #--------------------------------------------------------------------------
    # Storage Device Configuration Methods ------------------------------------
    #--------------------------------------------------------------------------

    def confirm_partitions(self) -> bool:
        output.warn("The following partitions will be created!")
        output.warn("Make sure this is what you want as these devices will likely be wiped!")

        for drive in self.config["drives"]:
            output.warn(f"\t- {drive}")
            for partition in self.config["drives"][drive]["partitions"]:
                output.warn(f"\t\t- {partition}")
            output.warn("")

        choice = output.get_input("Are you sure you would like to continue? (N/y)").lower()
        if choice == "y":
            return True
        else:
            return False

    #--------------------------------------------------------------------------

    def partition_drives(self):
        for drive in self.config["drives"]:
            output.substatus(f"Partitioning drive '{drive}'...")

            drive_config = fill_defaults(self.config["drives"][drive],
                                         Defaults.DRIVE)

            device_path = drive_config["device-path"]
            gpt         = drive_config["gpt"]

            self.drives[drive] = Drive(device_path=device_path,
                                       gpt=gpt)

            for uid in drive_config["partitions"]:
                output.substatus(f"Creating partition '{uid}'...", 2)

                partition_config = fill_defaults(drive_config["partitions"][uid],
                                                    Defaults.PARTITION)

                self.drives[drive].new_partition(partition_size=partition_config["size"],
                                                 start_sector=partition_config["start-sector"],
                                                 end_sector=partition_config["end-sector"],
                                                 type_code=partition_config["type-code"],
                                                 partition_label=partition_config["partition-label"],
                                                 uid=uid,
                                                 dry_run=self.dry_run)

                self.devices[uid] = self.drives[drive][uid]
            
            output.success(f"Drive '{drive}' has been successfully partitioned!", 1)

    #--------------------------------------------------------------------------

    def setup_raid_arrays(self):
        for uid in self.config["raid"]:
            output.substatus(f"Creating array '{uid}'...")

            raid_config = self.config["raid"][uid]
            raid_array_devices = []

            for raid_device_uid in raid_config["devices"]:
                output.substatus(f"Adding device '{raid_device_uid}' to array '{uid}'", 2)
                raid_array_devices.append(self.devices[raid_device_uid])
            
            self.devices[uid] = RaidArray(devices=raid_array_devices,
                                          array_name=raid_config["array-name"],
                                          level=raid_config["level"],
                                          dry_run=self.dry_run)

            output.success(f"RAID array '{uid}' has been successfully created!", 1)

    #--------------------------------------------------------------------------

    def encrypt_partitions(self):
        for uid in self.config["crypt"]:
            output.substatus(f"Encrypting device '{uid}'...")

            crypt_config = fill_defaults(self.config["crypt"][uid], Defaults.CRYPT)

            self.devices[uid].encrypt_partition(crypt_config["password"],
                                                crypt_config["crypt-label"],
                                                crypt_config["generate-keyfile"])

            if "load-early" in crypt_config and crypt_config["load-early"]:
                if self.early_crypt_device:
                    output.warn(f"Cannot set '{self.devices[uid].partition_label}' to load early.")
                    output.warn(f"'{self.early_crypt_device.partition_label}' is already set to load early.")
                    exit(1)
                else:
                    self.early_crypt_device = self.devices[uid]
                    output.info(f"Device '{uid}' set to decrypt in early userspace", 1)
            else:
                self.late_crypt_devices.append(self.devices[uid])

            output.success(f"Device '{uid}' has been successfully encrypted!", 1)

    def create_filesystems(self):
        for uid in self.config["filesystems"]:
            filesystem_config = fill_defaults(self.config["filesystems"][uid],
                                              Defaults.FILESYSTEM)

            output.substatus(f"Creating filesystem on '{uid}'...")

            self.devices[uid].new_filesystem(filesystem_config["filesystem"],
                                             filesystem_config["label"],
                                             filesystem_config["mountpoint"])

            output.success(f"Device '{uid}' has been successfully formatted!", 1)

        self.devices = dict(sorted(self.devices.items(), key=self.sort_by_mountpoint))
        print(self.devices)

    #--------------------------------------------------------------------------

    def run(self):
        output.info("Running...")

        if not self.confirm_partitions():
            output.info("Aborting...")
            exit(1)

        self.collect_crypt_passwords()
        self.collect_user_passwords()

        self.partition_drives()
        self.setup_raid_arrays()
        self.encrypt_partitions()
        self.create_filesystems()

#------------------------------------------------------------------------------

if __name__ == "__main__":
    main_parser = argparse.ArgumentParser(
        prog="excalibur",
        description="Template-based Arch Linux installer"
    )

    main = Excalibur(main_parser)

    main.run()

# EOF