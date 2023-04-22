import subprocess


KERNELS = ["zen", "hardened", "lts"]


# @TODO Add some type of logging

def pacstrap(target_mountpoint: str="/mnt",
             linux_kernel: str="",
             linux_firmware: bool=True,
             bootloader: str="grub",
             efibootmgr: bool=True,
             network_manager: bool=True,
             enable_ssh: bool=True,
             reflector: bool=True,
             ):

    # Ensure mirrors and keys are up to date
    update_command = ["pacman", "-Sy", "--noconfirm", "--color", "always", "archlinux-keyring"]
    # print(subprocess.run(update_command))
    print(" ".join(update_command))

    # Start building pacstrap command with base and base-devel as baseline packages
    pacstrap_command = ["pacstrap", target_mountpoint, "base", "base-devel"]

    # Append linux kernel and kernel header packages
    # Allow the user to specify zen, hardened or lts kernel
    if linux_kernel == "":
        pacstrap_command.append("linux")
        pacstrap_command.append("linux-headers")
    elif linux_kernel in KERNELS:
        pacstrap_command.append(f"linux-{linux_kernel}")
        pacstrap_command.append(f"linux-{linux_kernel}-headers")
    else:
        print(f"{linux_kernel} is not a valid kernel option")

    # Append linux-firmware by default
    if linux_firmware:
        pacstrap_command.append("linux-firmware")

    # Append a bootloader (grub by default)
    # Can be set to None to skip installing bootloader
    if bootloader:
        pacstrap_command.append(bootloader)

    # Append efibootmgr by default to allow for booting with efi
    if efibootmgr:
        pacstrap_command.append("efibootmgr")

    # Append networkmanager by default
    if network_manager:
        pacstrap_command.append("networkmanager")

    # Apppend openssh by default
    if enable_ssh:
        pacstrap_command.append("openssh")
    
    # Append reflector by default to ensure the fastest mirrors will be used
    if reflector:
        pacstrap_command.append("reflector")

    # print(subprocess.run(pacstrap_command))
    print(" ".join(pacstrap_command))


# EOF