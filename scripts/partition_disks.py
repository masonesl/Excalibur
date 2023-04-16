import subprocess


command_output = []


def open_disk(disk_config: str, efi: bool=True) -> list:

    # Open the given disk in gdisk
    gdisk = subprocess.Popen(["gdisk", disk_config["path"]], stdout=subprocess.PIPE,
                                                             stderr=subprocess.PIPE,
                                                             stdin=subprocess.PIPE)

    # Make the disk GPT if EFI is set to true or MBR if not
    command_output.append(gdisk.communicate("g" if efi else "d"))

    for partition in disk_config["partitions"]:

        if start_sec := partition["start-sector"]:
            command_output.append(gdisk.communicate(start_sec))
        else:
            command_output.append(gdisk.communicate(""))

        if end_sec := partition["end-sector"]:
            command_output.append(gdisk.communicate(end_sec))
        else:
            command_output.append(gdisk.communicate(""))

        if type_code := partition["type-code"]:
            command_output.append(gdisk.communicate(type_code))
        else:
            command_output.append(gdisk.communicate(""))

    