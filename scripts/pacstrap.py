from re import sub

import command_utils as cmd


KERNELS = ["zen", "hardened", "lts"]

#------------------------------------------------------------------------------

def tune_pacman(root: str="/", parallel_downloads: int=5):
    """Modify pacman.conf to enable colored output and set parallel downloads

    Args:
        root (str, optional): The system root to use ({root}/etc/pacman.conf). Defaults to "/".
        parallel_downloads (int, optional): How many parallel downloads to allow. Defaults to 5.
    """
    with open(f"{root}/etc/pacman.conf", "r") as pacman_conf_file:
        pacman_conf = pacman_conf_file.read()

    # Enable colored output
    pacman_conf = sub(r"\n#(Color)", r"\n\g<1>", pacman_conf)

    # Enable and set parallel downloads
    pacman_conf = sub(
        r"\n#?(ParallelDownloads = )\d+",
        rf"\n\g<1>{parallel_downloads}",
        pacman_conf
    )
    
    with open(f"{root}/etc/pacman.conf", "w") as pacman_conf_file:
        pacman_conf_file.write(pacman_conf)

#------------------------------------------------------------------------------

def update_pacman(dry_run: bool=False):
    """Make sure that mirrors and keyring are up to date so prevent errors when installing

    Args:
        dry_run (bool, optional): Print, don't run commands. Defaults to False.
    """
    cmd.execute("pacman --noconfirm -Sy archlinux-keyring", dry_run=dry_run)

#------------------------------------------------------------------------------

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

    # Start building pacstrap command with base and base-devel as baseline packages
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