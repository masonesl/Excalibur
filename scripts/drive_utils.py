import subprocess
from re import search


# @TODO Add logging


class Formattable:

    FILESYSTEMS = ["efi", "vfat", "ext4", "xfs", "swap"]

    def __init__(self, device_path: str,
                       partition_label: str):

        self.partition_path  = device_path
        self.partition_label = partition_label
        self.partition_uuid  = self.__get_blkid("PARTUUID")

        self.filesystem = None
        self.label      = None
        self.uuid       = None

        self.is_encrypted = False
        self.mapper_path  = None

    def __get_blkid(self, element: str):
        blkid_command = ["blkid", "-s", element, "-o", "value", self.partition_path]

        return subprocess.run(blkid_command, capture_output=True).stdout.decode().strip()

    def new_filesystem(self, filesystem: str,
                             label     : str="",
                             mountpoint: str="",
                             *options,):

        if filesystem not in Formattable.FILESYSTEMS:
            print(f"{filesystem} is not a valid filesystem")
            exit(1)

        match filesystem:
            case "efi":
                mkfs_command = ["mkfs.vfat", "-F32", "-n"]
            case "swap":
                mkfs_command = ["mkswap", "-L"]
            case _:
                mkfs_command = [f"mkfs.{filesystem}", "-L"]

        # Append filesystem label
        mkfs_command.append(label)

        # Append any other command options
        mkfs_command += options

        # Specify the block device to format
        mkfs_command.append(self.partition_path)

        # subprocess.run(mkfs_command, capture_output=True)

        print(" ".join(mkfs_command))

        # Store filesystem information
        self.filesystem = filesystem
        self.label      = label
        self.mountpoint = mountpoint
        self.uuid       = self.__get_blkid("UUID")

    def encrypt_partition(self, password   : str,
                                mapper_name: str,
                                **options,):

        # @TODO Add option for keyfile

        cryptsetup_format_command = ["cryptsetup", "-q", "luksFormat", self.partition_path]
        cryptsetup_open_command   = ["cryptsetup", "luksOpen", self.partition_path, mapper_name]

        # Append any additional options to each command
        if "format_options" in options:
            cryptsetup_format_command += options["format_options"]
        if "open_options" in options:
            cryptsetup_open_command   += options["open_options"]

        # cryptsetup_format = subprocess.Popen(cryptsetup_format_command, stdout=subprocess.PIPE,
        #                                                                 stdin =subprocess.PIPE,
        #                                                                 stderr=subprocess.PIPE)

        # cryptsetup_format.communicate(input=password.encode())

        print(" ".join(cryptsetup_format_command))

        # cryptsetup_open = subprocess.Popen(cryptsetup_open_command, stdout=subprocess.PIPE,
        #                                                             stdin =subprocess.PIPE,
        #                                                             stderr=subprocess.PIPE)

        # cryptsetup_open.communicate(input=password.encode())

        print(" ".join(cryptsetup_open_command))

        self.is_encrypted    = True
        self.real_path       = self.partition_path
        self.partition_path  = f"/dev/mapper/{mapper_name}"
        self.encrypt_uuid    = self.__get_blkid("UUID")

    
class RaidArray(Formattable):

    def __init__(self, devices   : list,
                       array_name: str,
                       level     : int=0,
                       *options):

        mdadm_command = ["mdadm", "--create", "--metadata=1.2"]

        # Set the RAID level
        mdadm_command.append(f"--level={level}")

        # Set the number of RAID devices
        mdadm_command.append(f"--raid-devices={len(devices)}")

        # Set the RAID array name
        mdadm_command.append(f"--name={array_name}")

        # Set the array to have the same name regardless of host
        mdadm_command.append("--hosthost=any")

        # Add any additional options to command
        mdadm_command += options

        # Allow for either devices or partitions to be added to the array
        for device in devices:
            try:
                mdadm_command.append(device.device_path)
            except AttributeError:
                mdadm_command.append(device.partition_path)

        # subprocess.run(mdadm_command, capture_output=True)

        print(" ".join(mdadm_command))

        super().__init__(device_path=f"/dev/mapper/{array_name}", 
                         partition_label=array_name)


class Partition(Formattable):

    def __init__(self, start_sector    : str="0",
                       end_sector      : str="0",
                       partition_size  : str="0",
                       type_code       : str="",
                       partition_label : str="",
                       partition_number: int= 1,
                       device_path     : str="",):

        sgdisk_command = ["sgdisk"]

        # Partition size command portion
        sgdisk_command.append("-n")

        if partition_size != "0":
            # Allow for specifying size OR start and end sectors
            # If size is not specified, it assumes start and end sectors are
            # This will be changed at some point
            start_sector = "0"
            end_sector   = f"+{partition_size}"

        sgdisk_command.append(f"{partition_number}:{start_sector}:{end_sector}")

        # Partition type code command portion
        sgdisk_command.append("-t")
        sgdisk_command.append(f"{partition_number}:{type_code}")

        # Partition label command portion
        sgdisk_command.append("-c")
        sgdisk_command.append(f"{partition_number}:{partition_label}")

        # Specify the drive via its device path
        sgdisk_command.append(device_path)

        # subprocess.run(sgdisk_command, capture_output=True)

        print(" ".join(sgdisk_command))

        partition_path = "{path}{sep}{num}".format(
            path=device_path,
            sep ="p" if search("\d{1}$", device_path) else "",
            num =partition_number
        )

        super().__init__(partition_path, partition_label)


class Drive:

    def __init__(self, device_path: str, gpt: bool=True):
        self.number_of_partitions = 0

        self.device_path = device_path
        self.is_gpt      = gpt

        self.partitions = {}

    def new_partition(self, start_sector   : str="0",
                            end_sector     : str="0",
                            partition_size : str="0",
                            type_code      : str="",
                            partition_label: str="",
                            uid            : str="",):

        self.number_of_partitions += 1

        self.partitions[uid] = Partition(
            start_sector,
            end_sector,
            partition_size,
            type_code,
            partition_label,
            self.number_of_partitions,
            self.device_path
        )

    def __getitem__(self, uid: str):
        return self.partitions[uid]

# EOF
