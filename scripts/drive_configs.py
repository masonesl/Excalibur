import subprocess


FILESYSTEMS = ["vfat", "swap", "ext4", "xfs"]


command_output = []


def partition(disk_config: dict, efi: bool=True) -> list:
    # @TODO Might make more sense to have this function handle single partitions
    #       instead of handling all of them

    sgdisk_command = ["sgdisk"]

    part_num = 1
    for partition in disk_config["partitions"].values():
        sgdisk_command.append("-n")
        sgdisk_command.append(f"{part_num}:{partition['start-sector']}:{partition['end-sector']}")

        sgdisk_command.append("-t")
        sgdisk_command.append(f"{part_num}:{partition['type-code']}")

        sgdisk_command.append("-c")
        sgdisk_command.append(f"{part_num}:{partition['label']}")
        
        part_num+=1

    sgdisk_command.append(disk_config["path"])

    command_output.append(subprocess.run(sgdisk_command, capture_output=True))


def format(filesystem_config: dict) -> list:

    if (filesystem:= filesystem_config["filesystem"]) not in FILESYSTEMS:
        print(f"{filesystem} not a valid filesystem")
        exit(1)

    mkfs_command = [f"mkfs.{filesystem}"]

    mkfs_command.append(filesystem_config["options"])

    mkfs_command.append("-n" if filesystem == "vfat" else "-L")
    mkfs_command.append(filesystem_config["label"])

    print(" ".join(mkfs_command))
