import subprocess

import command_utils as cmd


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
             dry_run: bool=False
             ):

    # Ensure mirrors and keys are up to date
    cmd.execute("pacman --color always --noconfirm -Sy archlinux-keyring", dry_run=dry_run)

    # Start building pacstrap command with base and base-devel as baseline packages
    pacstrap_command = ["pacstrap", target_mountpoint, "base", "base-devel"]
    pacstrap_command = f"pacstrap {target_mountpoint} base base-devel linux"

    # Append linux kernel and kernel header packages
    # Allow the user to specify zen, hardened or lts kernel
    if linux_kernel == "":
        pacstrap_command += " linux-headers"
    elif linux_kernel in KERNELS:
        pacstrap_command += f"-{linux_kernel} linux-{linux_kernel}-headers"
    else:
        print(f"{linux_kernel} is not a valid kernel option")

    # Append linux-firmware by default
    if linux_firmware:
        pacstrap_command += " linux-firmware"

    # Append a bootloader (grub by default)
    # Can be set to None to skip installing bootloader
    if bootloader:
        pacstrap_command += f" {bootloader}"

    # Append efibootmgr by default to allow for booting with efi
    if efibootmgr:
        pacstrap_command += " efibootmgr"

    # Append networkmanager by default
    if network_manager:
        pacstrap_command += " networkmanager"

    # Apppend openssh by default
    if enable_ssh:
        pacstrap_command += " openssh"
    
    # Append reflector by default to ensure the fastest mirrors will be used
    if reflector:
        pacstrap_command += " reflector"

    cmd.execute(pacstrap_command, dry_run=dry_run)


# EOF