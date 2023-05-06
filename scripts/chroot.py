from re import sub, findall

import command_utils as cmd
import output_utils  as output

from drive_utils import Formattable

#------------------------------------------------------------------------------

class Chroot:

    def __init__(self, target_mountpoint: str="/mnt", dry_run=False):
        # Mount all temporary API filesystems
        cmd.execute(f"mount -t proc /proc {target_mountpoint}/proc/", dry_run=dry_run)
        cmd.execute(f"mount --rbind /sys {target_mountpoint}/sys/", dry_run=dry_run)
        cmd.execute(f"mount --make-rslave {target_mountpoint}/sys/", dry_run=dry_run)
        cmd.execute(f"mount --rbind /dev {target_mountpoint}/dev/", dry_run=dry_run)
        cmd.execute(f"mount --make-rslave {target_mountpoint}/dev/", dry_run=dry_run)
        cmd.execute(f"mount --rbind /run {target_mountpoint}/run/", dry_run=dry_run)
        cmd.execute(f"mount --make-slave {target_mountpoint}/run/", dry_run=dry_run)

        # Mount EFI variables for UEFI bootloader configuration
        cmd.execute(
            f"mount --rbind /sys/firmware/efi/efivars {target_mountpoint}/sys/firmware/efi/efivars",
            dry_run=dry_run)

        # Copy DNS details to new root
        cmd.execute(f"cp /etc/resolv.conf {target_mountpoint}/etc/resolv.conf", dry_run=dry_run)

        self.target    = target_mountpoint
        self.dry_run   = dry_run
        self.installer = "pacman"

        self.system_groups     = self.__get_groups()

    #--------------------------------------------------------------------------

    def __enter__(self):
        return self

    #--------------------------------------------------------------------------

    def __wrap_chroot(self, command: str, pipe_mode: int=3, wait_for_proc=True, user: str=""):
        """Execute a command in the chroot environment

        Args:
            command (str): Command to be executed
            pipe_mode (int, optional): Octal code to specify which data streams to set to subprocess.PIPE. Defaults to 3.
            wait_for_proc (bool, optional): Whether or not to wait for the command to finish executing. Defaults to True.

        Returns:
            tuple: If wait_for_proc is True
            subprocess.Popen: If wait_for_proc is False
        """
        return cmd.execute(
            f"chroot {f'--userspec={user} ' if user else ''}{self.target} sh -c '{command}'",
            pipe_mode,
            self.dry_run,
            wait_for_proc
        )

    #--------------------------------------------------------------------------

    def __add_hook(self, preceding_hook: str, hook: str):
        """Add a hook to /etc/mkinitcpio.conf

        Args:
            preceding_hook (str): The hook directly before the hook to be added
            hook (str): The actual hook to be added
        """

        with open(f"{self.target}/etc/mkinitcpio.conf", "r") as initrd_conf_file:
            initrd_conf = initrd_conf_file.read()

        initrd_conf = sub(
            rf'\nHOOKS=\(.*{preceding_hook}',
            rf'\g<0> {hook}',
            initrd_conf
        )

        with open(f"{self.target}/etc/mkinitcpio.conf", "w") as initrd_conf_file:
            initrd_conf_file.write(initrd_conf)

    #--------------------------------------------------------------------------

    def __add_kernel_parameter(self, parameter: str):
        with open(f"{self.target}/etc/default/grub", "r") as grub_file:
            grub_config = grub_file.read()

        grub_config = sub(
            r'\nGRUB_CMDLINE_LINUX_DEFAULT="',
            rf'\g<0>{parameter} ',
            grub_config
        )

        with open(f"{self.target}/etc/default/grub", "w") as grub_file:
            grub_file.write(grub_config)

    #--------------------------------------------------------------------------

    def __get_groups(self):
        groups = []
        with open(f"{self.target}/etc/group", "r") as groups_file:
            for groupline in groups_file.readlines():
                groups.append(groupline.split(":")[0])

        return groups

    #--------------------------------------------------------------------------

    def configure_clock(self, timezone: str="",
                              hardware_utc: bool=True,
                              enable_ntp: bool=True):

        # Create a symlink from the timezone file to /etc/localtime
        if timezone:
            cmd.execute(
                f"ln -sf {self.target}/usr/share/zoneinfo/{timezone} {self.target}/etc/localtime",
                dry_run=self.dry_run
            )

        # Configure the hardware clock to system time (with UTC if desired)
        self.__wrap_chroot(f"hwclock --systohc {'--utc' if hardware_utc else ''}")

        # Enable systemd-timesyncd if desired
        if enable_ntp:
            self.__wrap_chroot("systemctl enable systemd-timesyncd")

    #--------------------------------------------------------------------------

    def configure_locales(self, locale_gen: list=["en_US.UTF-8 UTF-8"],
                                locale_conf: str="en_US.UTF-8"):

        # Uncomment each specified locale in /etc/locale.gen
        with open(f"{self.target}/etc/locale.gen", "r") as locale_gen_file:
            locale_file_data = locale_gen_file.read()

        for locale in locale_gen:
            locale_file_data = locale_file_data.replace(f"#{locale}", locale)

        with open(f"{self.target}/etc/locale.gen", "w") as locale_gen_file:
            locale_gen_file.write(locale_file_data)

        # Generate locales
        self.__wrap_chroot("locale-gen")

        # Set the LANG variable to desired locale
        with open(f"{self.target}/etc/locale.conf", "w") as locale_conf_file:
            locale_conf_file.write(f"LANG={locale_conf}")

    #--------------------------------------------------------------------------

    def configure_hosts(self):
        # Add localhost entries in /etc/hosts for both IPv4 and IPv6
        with open(f"{self.target}/etc/hosts", "a") as hosts_file:
            hosts_file.write("127.0.0.1\tlocalhost\n")
            hosts_file.write("::1\t\tlocalhost\n")

    #--------------------------------------------------------------------------

    def set_hostname(self, hostname: str="myhostname"):
        with open(f"{self.target}/etc/hostname", "w") as hostname_file:
            hostname_file.write(hostname)

    #--------------------------------------------------------------------------

    def set_root_password(self, root_password: str):
        root_password_proc = self.__wrap_chroot("passwd", 7, wait_for_proc=False)
        if not self.dry_run:
            root_password_proc.communicate(f"{root_password}\n{root_password}".encode())

    #--------------------------------------------------------------------------

    def configure_user(self, username: str,
                             shell   : str,
                             home    : str,
                             comment : str,
                             groups  : list,
                             password: str):
        
        self.__wrap_chroot(f"useradd -m{f' -d {home}' if home else ''} {username}")

        if shell:
            # Try to install shell if it does not exist
            with open(f"{self.target}/etc/shells", "r") as shells_file:

                shell_installed = False
                for shell_line in shells_file.readlines()[3:]:
                    if shell_line.strip() == shell:
                        shell_installed = True

                if not shell_installed:
                    self.__wrap_chroot(f"pacman --noconfirm -S {shell.split('/')[-1]}")
                    
            self.__wrap_chroot(f"usermod -s {shell} {username}")

        if comment:
            self.__wrap_chroot(f"usermod -c {comment} {username}")

        if groups:
            for group in groups:
                # Create group if it does not exist
                if group not in self.system_groups:
                    self.__wrap_chroot(f"groupadd {group}")
                    self.system_groups.append(group)
                
                self.__wrap_chroot(f"usermod -a -G {group}, {username}")

        passwd_proc = self.__wrap_chroot(f"passwd {username}", 7, wait_for_proc=False)
        if not self.dry_run:
            passwd_proc.communicate(f"{password}\n{password}".encode())

    #--------------------------------------------------------------------------

    def configure_early_crypt(self, encrypted_block: Formattable):
        self.__add_hook("block", "encrypt")

        self.__add_kernel_parameter(
            f"cryptdevice=UUID={encrypted_block.uuid}:{encrypted_block.encrypt_label}"
        )

    #--------------------------------------------------------------------------

    def configure_late_crypt(self, encrypted_block: Formattable):
        crypttab_line = f"{encrypted_block.encrypt_label}\tUUID={encrypted_block.uuid}"

        if encrypted_block.uses_keyfile:
            cmd.execute(f"cp /tmp/{encrypted_block.encrypt_label}.key {self.target}/etc/cryptsetup-keys.d/")
            crypttab_line += f"\t/etc/cryptsetup-keys.d/{encrypted_block.encrypt_label}.key"

        with open(f"{self.target}/etc/crypttab", "a") as crypttab_file:
            crypttab_file.write(crypttab_line)

    #--------------------------------------------------------------------------

    def configure_raid(self):
        self.__wrap_chroot("pacman --noconfirm -S mdadm")

        # Scan for the current RAID arrays and their configurations and add them to the mdadm.conf file
        raid_conf = cmd.execute("mdadm --detail --scan", 6, self.dry_run)
        if not self.dry_run:
            with open(f"{self.target}/etc/mdadm.conf", "a") as mdadm_conf_file:
                mdadm_conf_file.write(raid_conf[0].decode())

        # Add the mdadm_udev hook to the initramfs to load RAID arrays on boot
        self.__add_hook("block", "mdadm_udev")

    #--------------------------------------------------------------------------

    def generate_initramfs(self):
        self.__wrap_chroot("mkinitcpio -P")

    #--------------------------------------------------------------------------

    def enable_aur(self, helper: str):
        helper_url = f"https://aur.archlinux.org/{helper}.git"
        self.installer = helper

        # Create a temporary user to run makepkg
        self.__wrap_chroot("useradd -M -N aurtmp")

        # Create a drop in sudo configuration file for the temporary user
        with open(f"{self.target}/etc/sudoers.d/aurtmp", "w") as sudoers:
            sudoers.write("aurtmp ALL=(ALL:ALL) NOPASSWD: ALL")
        
        # Download git and clone the AUR helper repo
        self.__wrap_chroot("pacman --noconfirm -S git")
        self.__wrap_chroot(f"git clone {helper_url} /tmp/{helper}", user="aurtmp")

        # Build and install the helper
        self.__wrap_chroot(f"cd /tmp/{helper} && makepkg -S", user="aurtmp")
        self.__wrap_chroot(f"cd /tmp/{helper} && makepkg --noconfirm -i", user="aurtmp")

    #--------------------------------------------------------------------------

    def install_packages(self, packages: list):
        if self.installer == "pacman":
            self.__wrap_chroot(f"pacman --noconfirm -Syu {' '.join(packages)}")
        else:
            self.__wrap_chroot(
                f"{self.installer.strip('-bin')} --noconfirm -Syu {' '.join(packages)}",
                user="aurtmp"
            )

    #--------------------------------------------------------------------------

    def enable_services(self, services: list):
        for service in services:
            self.__wrap_chroot(f"systemctl enable {service}")

    #--------------------------------------------------------------------------

    def exit(self):
        # Clean up aur helper user if invoked
        if self.installer != "pacman":
            self.__wrap_chroot("userdel aurtmp")
            self.__wrap_chroot("rm /etc/sudoers.d/aurtmp")

        # Unmount all API filesystems from new root
        cmd.execute(f"umount -R {self.target}/proc/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/sys/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/dev/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/run/", dry_run=self.dry_run)

    #--------------------------------------------------------------------------

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit()


