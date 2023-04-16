import subprocess


command_output = []


def partition(disk_config: dict, efi: bool=True) -> list:

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



