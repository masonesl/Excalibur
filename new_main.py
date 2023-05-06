import os
import sys
import pickle
import argparse
import traceback

from getpass import getpass

sys.path.append(f"{os.getcwd()}/scripts")

from scripts.pacstrap      import tune_pacman, update_pacman, pacstrap
from scripts.drive_utils   import Drive, RaidArray
from scripts.config_utils  import Config
from scripts.chroot        import Chroot

import scripts.command_utils as cmd
import scripts.output_utils  as output


class Excalibur:

    TASK_KEY = {
        0: "Partition Drives",
        1: "Create RAID arrays",
        2: "Encrypt Partitions",
        3: "Create Filesystems",
        4: "Pacstrap New Root",
        5: "Configure New Root"
    }

    CHROOT_TASK_KEY = {
        0: "Configure Clock",
        1: "Configure Locales",
        2: "Set Default Hosts",
        3: "Set Hostname",
        4: "Configure Users",
        5: "Configure Crypt",
        6: "Configure RAID",
        7: "Enable AUR",
        8: "Install Packages",
        9: "Enable Services"
    }

    def __init__(self, parser: argparse.ArgumentParser):
        self.args = self.__parse_args(parser)

        self.config = Config(self.args.CONFIG_FILE_PATH)

        # Exit and print missing options if there are any
        if self.config.missing_required:
            output.error(f"Missing required options in {self.args.CONFIG_FILE_PATH}:\n")
            for option in self.config.missing_required:
                output.error(" >> ".join(option))
            raise Exception

        # Print warnings if passwords were found in the config file
        if warnings := self.config.password_warnings["users"]:
            output.warn(f"Do not store user passwords in {self.args.CONFIG_FILE_PATH}")
            output.warn(
                f"The following users' passwords will be overwritted: {', '.join(warnings)}"
                )
        if warnings := self.config.password_warnings["encryption"]:
            output.warn(f"Do not store encryption passwords in {self.args.CONFIG_FILE_PATH}")
            output.warn(
                f"The following encrypted device passwords will be overwritted: {', '.join(warnings)}"
                )

        self.dry_run = self.args.DRY_RUN
        self.target  = self.args.MOUNTPOINT

        # Placeholder root password until it gets set
        # Only should be used when dry running
        self.root_password = "password"

        # Stores physical device information
        self.drives = {}
        # Stores formattable devices like partitions and RAID arrays
        self.devices = {}

        # List of RAID arrays
        self.raid_arrays = []

        # List of devices to be unlocked in late userspace via /etc/crypttab
        self.late_crypt_devices = []
        # Device to be unlock in early userspace via initrd
        # For now, only one device can be set
        self.early_crypt_device = None

        self.status = {}
        self.chroot_status = {}

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
        
        parser.add_argument("--no-partition-drives",
                            help="Skip partitioning drives",
                            dest="PARTITION_DRIVES",
                            action="store_false",
                            default=True)
        
        parser.add_argument("--no-create-raid",
                            help="Skip creating RAID arrays",
                            dest="CREATE_RAID_ARRAYS",
                            action="store_false",
                            default=True)
        
        parser.add_argument("--no-create-crypt",
                            help="Skip creating encrypted devices",
                            dest="CREATE_CRYPT",
                            action="store_false",
                            default=True)
        
        parser.add_argument("--no-create-filesystems",
                            help="Skip creating filesystems",
                            dest="CREATE_FILESYSTEMS",
                            action="store_false",
                            default=True)
        
        parser.add_argument("--no-pacstrap",
                            help="Skip pacstrapping the new root",
                            dest="PACSTRAP",
                            action="store_false",
                            default=True)
        
        parser.add_argument("--no-chroot",
                            help="Skip configuring the new root",
                            dest="CHROOT",
                            action="store_false",
                            default=True)

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

    @staticmethod
    def notify_status(task_key: dict, status: dict) -> int:
        line = lambda task, task_key : f"[{task}] {task_key[task]}"

        default = None
        for task in task_key:
            # Indicate that the task has not been tried
            if task not in status:
                output.warn(line(task, task_key))

            # Indicate that the task has successfully finished
            elif status[task]["Status"] == 0:
                output.success(line(task, task_key))

            # Indicate that the task was started, but not finished
            elif status[task]["Status"] == 1:
                output.error(f"{line(task, task_key)} (Interrupted)")
                default = task

        valid_choice = False
        while not valid_choice:
            try:
                choice = int(output.get_input(f"Select from where to continue from ({default})") or default)
                if choice >= len(task_key) or choice < 0:
                    raise ValueError
                valid_choice = True
            except ValueError:
                output.error(f"Please, enter a number from {0} to {len(task_key) - 1}")

        return choice

    #--------------------------------------------------------------------------
    # Password Collection Methods ---------------------------------------------
    #--------------------------------------------------------------------------

    def collect_user_passwords(self):
        self.root_password = self.get_password("Set password for root",
                                               "Repeat password for root")

        for user in self.config.users:
            self.config.users[user]["password"] = self.get_password(
                f"Set password for {user}",
                f"Repeat password for {user}"
            )

    #--------------------------------------------------------------------------

    def collect_crypt_passwords(self):
        for crypt_device in self.config.crypt:
            self.config.crypt[crypt_device]["password"] = self.get_password(
                f"Set encrypt password for {crypt_device}",
                f"Repeat password for {crypt_device}"
            )

    #--------------------------------------------------------------------------

    def check_state(self, parser: argparse.ArgumentParser):
        new_args = self.__parse_args(parser)

        output.warn("Previous session found\n")
        output.warn("Choose from where you would like to continue from\n")
        
        task_choice = self.notify_status(Excalibur.TASK_KEY, self.status)

        for task in range(len(self.status)-1, task_choice-1, -1):
            del self.status[task]

        if len(self.chroot_status) != 0:
            output.warn("It looks like the new root has been partially configured\n")
            output.warn("Choose from where you would like to continue from in the chroot\n")

            chroot_task_choice = self.notify_status(Excalibur.CHROOT_TASK_KEY, self.chroot_status)

            for task in range(len(self.chroot_status)-1, chroot_task_choice-1, -1):
                del self.chroot_status[task]

    #--------------------------------------------------------------------------
    # Storage Device Configuration Methods ------------------------------------
    #--------------------------------------------------------------------------

    def confirm_partitions(self) -> bool:
        output.warn("The following partitions will be created!")
        output.warn("Make sure this is what you want as these devices will likely be wiped!")

        for drive in self.config.drives:
            output.warn(f"\t- {drive}")
            for partition in self.config.drives[drive]["partitions"]:
                output.warn(f"\t\t- {partition}")
            output.warn("")

        choice = output.get_input("Are you sure you would like to continue? (N/y)").lower()
        if choice == "y":
            return True
        else:
            return False

    #--------------------------------------------------------------------------

    def partition_drives(self):
        for drive in self.config.drives:
            output.substatus(f"Partitioning drive '{drive}'...")

            drive_config = self.config.drives[drive]

            device_path = drive_config["device-path"]
            gpt         = drive_config["gpt"]

            self.drives[drive] = Drive(device_path=device_path,
                                       gpt=gpt)

            for uid in drive_config["partitions"]:
                output.substatus(f"Creating partition '{uid}'...", 2)

                partition_config = drive_config["partitions"][uid]

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
        for uid in self.config.raid:
            output.substatus(f"Creating array '{uid}'...")

            raid_config = self.config.raid[uid]
            raid_array_devices = []

            for raid_device_uid in raid_config["devices"]:
                output.substatus(f"Adding device '{raid_device_uid}' to array '{uid}'", 2)
                raid_array_devices.append(self.devices[raid_device_uid])
            
            self.devices[uid] = RaidArray(devices=raid_array_devices,
                                          array_name=raid_config["array-name"],
                                          level=raid_config["level"],
                                          dry_run=self.dry_run)

            self.raid_arrays.append(self.devices[uid])

            output.success(f"RAID array '{uid}' has been successfully created!", 1)

    #--------------------------------------------------------------------------

    def encrypt_partitions(self):
        for uid in self.config.crypt:
            output.substatus(f"Encrypting device '{uid}'...")

            crypt_config = self.config.crypt[uid]

            self.devices[uid].encrypt_partition(crypt_config["password"],
                                                crypt_config["crypt-label"],
                                                crypt_config["generate-keyfile"])

            if "load-early" in crypt_config and crypt_config["load-early"]:
                if self.early_crypt_device:
                    output.error(f"Cannot set '{self.devices[uid].partition_label}' to decrypt early.")
                    output.error(f"'{self.early_crypt_device.partition_label}' is already set to decrypt early.")
                    raise Exception
                else:
                    self.early_crypt_device = self.devices[uid]
                    output.info(f"Device '{uid}' set to decrypt in early userspace", 1)
            else:
                self.late_crypt_devices.append(self.devices[uid])

            output.success(f"Device '{uid}' has been successfully encrypted!", 1)

    #--------------------------------------------------------------------------

    def create_filesystems(self):
        for uid in self.config.filesystems:
            filesystem_config = self.config.filesystems[uid]

            output.substatus(f"Creating filesystem on '{uid}'...")

            self.devices[uid].new_filesystem(filesystem_config["filesystem"],
                                             filesystem_config["label"],
                                             filesystem_config["mountpoint"])

            output.success(f"Device '{uid}' has been successfully formatted!", 1)

        # Sort mountable devices by their mountpoints 
        self.devices = dict(sorted(self.devices.items(), key=self.sort_by_mountpoint))

    #--------------------------------------------------------------------------

    def mount_filesystems(self):
        for uid in self.devices:
            self.devices[uid].mount_filesystem(f"{self.target}{self.devices[uid].mountpoint}")

    #--------------------------------------------------------------------------

    def bootstrap_newroot(self):
        # Tune pacman in the live environment
        if not self.dry_run:
            tune_pacman()
        update_pacman(self.dry_run)

        pacstrap(
            self.target,
            self.config.kernel,
            self.config.firmware,
            self.config.boot["bootloader"],
            self.config.boot["efi"],
            self.config.networkmanager,
            self.config.ssh,
            self.config.reflector,
            self.dry_run
        )

        # Tune pacman in the new target environment
        tune_pacman(self.target)

    #--------------------------------------------------------------------------

    def run(self):
        output.info("Running...")

        if not self.dry_run:
            self.collect_crypt_passwords()
            self.collect_user_passwords()

        if self.config.drives and self.args.PARTITION_DRIVES and 0 not in self.status:
            if not self.confirm_partitions():
                output.info("Aborting...")
                raise Exception

            self.status[0] = {\
                "Task": Excalibur.TASK_KEY[0],
                "Status": 1
            }

            output.status("Creating partitions...")
            self.partition_drives()
            output.success("Partitions successfully created!")

            self.status[0]["Status"] = 0

        if self.config.raid and self.args.CREATE_RAID_ARRAYS and 1 not in self.status:
            self.status[1] = {
                "Task" : Excalibur.TASK_KEY[1],
                "Status" : 1
            }

            output.status("Creating RAID arrays...")
            self.setup_raid_arrays()
            output.success("RAID arrays successfully created!")

            self.status[1]["Status"] = 0

        if self.config.crypt and self.args.CREATE_CRYPT and 2 not in self.status:
            self.status[2] = {
                "Task" : Excalibur.TASK_KEY[2],
                "Status" : 1
            }

            output.status("Encrypting block devices...")
            self.encrypt_partitions()
            output.success("Block devices successfully encrypted!")

            self.status[2]["Status"] = 0

        if self.config.filesystems and self.args.CREATE_FILESYSTEMS and 3 not in self.status:
            self.status[3] = {
                "Task" : Excalibur.TASK_KEY[3],
                "Status" : 1
            }

            output.status("Creating filesystems...")
            self.create_filesystems()
            output.success("Filesystems successfully created!")

            output.status("Mounting filesystems...")
            self.mount_filesystems()
            output.success("Filesystems successfully mounted!")

            self.status[3]["Status"] = 0

        if self.args.PACSTRAP and 4 not in self.status:
            print(self.args.PACSTRAP)
            self.status[4] = {
                "Task" : Excalibur.TASK_KEY[3],
                "Status" : 1
            }

            output.status("Bootstrapping the new root...")
            self.bootstrap_newroot()
            output.success("New root sucessfully bootstrapped")

            self.status[4]["Status"] = 0

        if self.args.CHROOT and 5 not in self.status:
            self.status[5] = {
                "Task" : Excalibur.TASK_KEY[5],
                "Status" : 1
            }

            output.status("Creating chroot environment...")
            with Chroot(self.target, self.dry_run) as chroot_env:

                if 0 not in self.chroot_status:
                    self.chroot_status[0] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[0],
                        "Status": 1
                    }

                    output.substatus("Configuring clock...")
                    chroot_env.configure_clock(
                        self.config.clock["timezone"],
                        self.config.clock["hardware-utc"],
                        self.config.clock["enable-ntp"]
                    )

                    self.chroot_status[0]["Status"] = 0

                if 1 not in self.chroot_status:
                    self.chroot_status[1] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[1],
                        "Status": 1
                    }

                    output.substatus("Configuring locales...")
                    chroot_env.configure_locales(
                        self.config.locales["locale-gen"],
                        self.config.locales["locale-conf"]
                    )

                    self.chroot_status[1]["Status"] = 0

                if 2 not in self.chroot_status:
                    self.chroot_status[2] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[2],
                        "Status": 1
                    }

                    output.info("Set default /etc/hosts", 1)
                    chroot_env.configure_hosts()

                    self.chroot_status[2]["Status"] = 0

                if 3 not in self.chroot_status:
                    self.chroot_status[3] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[3],
                        "Status": 1
                    }

                    output.info(f"Set default hostname to {self.config.hostname}", 1)
                    chroot_env.set_hostname(self.config.hostname)

                    self.chroot_status[3]["Status"] = 0

                if 4 not in self.chroot_status:
                    self.chroot_status[4] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[4],
                        "Status": 1
                    }

                    output.substatus("Configuring users...")
                    output.info("Set root password", 2)
                    chroot_env.set_root_password(self.root_password)

                    for user in self.config.users:
                        output.substatus(f"Configuring user {user}...", 2)
                        user_config = self.config.users[user]

                        chroot_env.configure_user(
                            user,
                            user_config["shell"],
                            user_config["home"],
                            user_config["comment"],
                            user_config["groups"],
                            user_config["password"]
                        )

                    self.chroot_status[4]["Status"] = 0

                if 5 not in self.chroot_status:
                    self.chroot_status[5] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[5],
                        "Status": 1
                    }

                    output.substatus("Configuring encrypted devices...")
                    if self.early_crypt_device:
                        output.info(f"Configuring device {self.early_crypt_device.encrypt_label} to decrypt in early userspace", 1)
                        chroot_env.configure_early_crypt(self.early_crypt_device)
                    for crypt_dev in self.late_crypt_devices:
                        chroot_env.configure_late_crypt(crypt_dev)

                    self.chroot_status[5]["Status"] = 0

                if 6 not in self.chroot_status:
                    self.chroot_status[6] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[6],
                        "Status": 1
                    }
                    
                    output.substatus("Configure RAID arrays...")
                    chroot_env.configure_raid()

                    self.chroot_status[6]["Status"] = 0

                if 7 not in self.chroot_status:
                    self.chroot_status[7] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[7],
                        "Status": 1
                    }

                    output.substatus("Configuring AUR...")
                    chroot_env.enable_aur(self.config.aur_helper)

                    self.chroot_status[7]["Status"] = 0

                if 8 not in self.chroot_status:
                    self.chroot_status[8] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[8],
                        "Status": 1
                    }

                    output.substatus("Installing packages...")
                    chroot_env.install_packages(self.config.packages)

                    self.chroot_status[8]["Status"] = 0


                if 9 not in self.chroot_status:
                    self.chroot_status[9] = {
                        "Task": Excalibur.CHROOT_TASK_KEY[9],
                        "Status": 1
                    }

                    output.substatus("Enabling services...")
                    chroot_env.enable_services(self.config.services)

                    self.chroot_status[9]["Status"] = 0

            self.status[5]["Status"] = 0

#------------------------------------------------------------------------------

if __name__ == "__main__":
    main_parser = argparse.ArgumentParser(
        prog="excalibur",
        description="Template-based Arch Linux installer"
    )

    if os.path.isfile("cache"):
        with open("cache", "rb") as cache_file:
            main = pickle.load(cache_file)
            main.check_state(main_parser)
    else:
        main = Excalibur(main_parser)

    try:
        main.run()
    except:
        output.error(f"Program Error\n{traceback.format_exc()}")
    finally:
        if (i := output.get_input("Would you like to save the program state? (Y/n)").lower()) == "y" or i == "":
            with open("cache", "wb") as cache_file:
                pickle.dump(main, cache_file)

# EOF