from re import search

import command_utils as cmd
import output_utils  as output

#------------------------------------------------------------------------------

class Formattable:

    FILESYSTEMS = ["efi", "vfat", "ext4", "xfs", "swap"]

    #--------------------------------------------------------------------------

    def __init__(self, device_path    : str,
                       partition_label: str,
                       dry_run        : bool=False):

        self.partition_path  = device_path
        self.partition_label = partition_label
        self.partition_uuid  = self.__get_blkid("PARTUUID")

        self.filesystem = None
        self.label      = None
        self.mountpoint = None
        self.uuid       = None

        self.uses_keyfile  = False
        self.mapper_path   = None
        self.encrypt_uuid  = None
        self.encrypt_label = None

        self.dry_run = dry_run

    #--------------------------------------------------------------------------

    def __get_blkid(self, element: str):
        return cmd.execute(
            f"blkid -s {element} -o value {self.partition_path}", 4)[0].decode().strip()

    #--------------------------------------------------------------------------

    def new_filesystem(self, filesystem: str,
                             label     : str="",
                             mountpoint: str="",
                             options   : str="",):

        if filesystem not in Formattable.FILESYSTEMS:
            output.warn(f"{filesystem} is not a valid filesystem")
            exit(1)

        match filesystem:
            case "efi":
                mkfs_command = "mkfs.vfat -F32 -n"
            case "swap":
                mkfs_command = "mkswap -L"
            case _:
                mkfs_command = f"mkfs.{filesystem} -L"

        mkfs_command += f" {label}"

        # Append any other command options
        mkfs_command += f" {options}"

        # Specify the block device to format
        mkfs_command += f" {self.partition_path}"

        cmd.execute(mkfs_command, dry_run=self.dry_run)

        # Store filesystem information
        self.filesystem = filesystem
        self.label      = label
        self.mountpoint = mountpoint
        self.uuid       = self.__get_blkid("UUID")

    #--------------------------------------------------------------------------

    def encrypt_partition(self, password   : str,
                                mapper_name: str,
                                keyfile    : bool=True,
                                **options,):

        if "format-options" not in options:
            options["format-options"] = ""
        if "open-options" not in options:
            options["open-options"] = ""

        if keyfile:
            # Create the keyfile in /tmp
            cmd.execute(f"dd bs=512 count=4 if=/dev/random of=/tmp/{mapper_name}.key iflag=fullblock")

            cryptsetup_format_command = f"cryptsetup --key-file /root/ramfs/{mapper_name}.key -q"
            cryptsetup_open_command   = f"cryptsetup --key-file /root/ramfs/{mapper_name}.key"
            
            self.uses_keyfile = True
        else:
            cryptsetup_format_command = "cryptsetup -q"
            cryptsetup_open_command   = "cryptsetup"

        cryptsetup_format_command += f" {options['format-options']} luksFormat {self.partition_path}"
        cryptsetup_open_command   += f" {options['open-options']} luksOpen {self.partition_path} {mapper_name}"

        luksformat_proc = cmd.execute(cryptsetup_format_command, 7, self.dry_run, False)
        if not self.dry_run:
            luksformat_proc.communicate(password.encode())

        luksopen_proc = cmd.execute(cryptsetup_open_command, 7, self.dry_run, False)
        if not self.dry_run:
            luksopen_proc.communicate(password.encode())

        self.real_path       = self.partition_path
        self.partition_path  = f"/dev/mapper/{mapper_name}"
        self.encrypt_uuid    = self.__get_blkid("UUID")
        self.encrypt_label   = mapper_name

    #--------------------------------------------------------------------------

    def mount_filesystem(self, override_mount=""):
        match self.filesystem:
            case None:
                return
            case "swap":
                cmd.execute(f"swapon {self.partition_path}", dry_run=self.dry_run)
            case _:
                cmd.execute(
                    f"mount -m {self.partition_path} {override_mount if override_mount else self.mountpoint}",
                    dry_run=self.dry_run)

#------------------------------------------------------------------------------    

class RaidArray(Formattable):

    def __init__(self, devices   : list,
                       array_name: str,
                       level     : int=0,
                       options   : str="",
                       dry_run   : bool=False):

        mdadm_command = f"mdadm --create --metadata=1.2 "

        # Set the RAID level
        mdadm_command += f"--level={level} "

        # Set the number of RAID devices
        mdadm_command += f"--raid-devices={len(devices)} "

        # Set the RAID array name
        mdadm_command += f"--name={array_name} "

        # Set the array to have the same name regardless of host
        mdadm_command += "--homehost=any" 

        # Add any additional options to command
        mdadm_command += options

        mdadm_command += f" /dev/md/{array_name} "

        # Allow for either devices or partitions to be added to the array
        for device in devices:
            try:
                mdadm_command += f"{device.device_path} "
            except AttributeError:
                mdadm_command += f"{device.partition_path} "

        cmd.execute(mdadm_command, dry_run=dry_run)

        super().__init__(device_path=f"/dev/md/{array_name}", 
                         partition_label=array_name,
                         dry_run=dry_run)

#------------------------------------------------------------------------------

class Partition(Formattable):

    def __init__(self, start_sector    : str="0",
                       end_sector      : str="0",
                       partition_size  : str="0",
                       type_code       : str="",
                       partition_label : str="",
                       partition_number: int= 1,
                       device_path     : str="",
                       dry_run         : bool=False):

        if partition_size != "0":
            # Allow for specifying size OR start and end sectors
            # If size is not specified, it assumes start and end sectors are
            # This will be changed at some point
            start_sector = "0"
            end_sector   = f"+{partition_size}"

        sgdisk_command = f"sgdisk -n {partition_number}:{start_sector}:{end_sector} "

        # Partition type code command portion
        if type_code:
            sgdisk_command += f"-t {partition_number}:{type_code} "

        # Partition label command portion
        if partition_label:
            sgdisk_command += f"-c {partition_number}:'{partition_label}' "

        # Specify the drive via its device path
        sgdisk_command += device_path

        cmd.execute(sgdisk_command, dry_run=dry_run)

        partition_path = "{path}{sep}{num}".format(
            path=device_path,
            sep ="p" if search("\d{1}$", device_path) else "",
            num =partition_number
        )

        super().__init__(partition_path, partition_label, dry_run=dry_run)

#------------------------------------------------------------------------------

class Drive:

    def __init__(self, device_path: str, gpt: bool=True):
        self.number_of_partitions = 0

        self.device_path = device_path
        self.is_gpt      = gpt

        self.partitions = {}

    #--------------------------------------------------------------------------

    def new_partition(self, start_sector   : str="0",
                            end_sector     : str="0",
                            partition_size : str="0",
                            type_code      : str="",
                            partition_label: str="",
                            uid            : str="",
                            dry_run        : bool=False):

        self.number_of_partitions += 1

        self.partitions[uid] = Partition(
            start_sector,
            end_sector,
            partition_size,
            type_code,
            partition_label,
            self.number_of_partitions,
            self.device_path,
            dry_run
        )

    #--------------------------------------------------------------------------

    def __getitem__(self, uid: str):
        return self.partitions[uid]


# EOF