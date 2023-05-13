from re import (
    subn as resubn,
    sub  as resub
)

from os import listdir

import command_utils as cmd
import output_utils  as output

from drive_utils import Formattable

#------------------------------------------------------------------------------

class Chroot:

    def __init__(
        self,
        target_mountpoint: str,
        dry_run          : bool,
        efi_directory    : str
    ):

        mount = lambda mount_options, mount_dir : \
            cmd.execute(
                f"mount {mount_options} {target_mountpoint}{mount_dir}",
                dry_run=dry_run
            )
      
        # Mount all temporary API filesystems
        mount("-t proc /proc", "/proc/")
        mount("--rbind /sys", "/sys/")
        mount("--make-rslave", "/sys/")
        mount("--rbind /dev", "/dev/")
        mount("--make-rslave", "/dev")
        mount("--rbind /run", "/run/")
        mount("--make-slave", "/run/")

        # Mount EFI variables for UEFI bootloader configuration
        mount("--rbind /sys/firmware/efi/efivars", "/sys/firmware/efi/efivars")

        # Copy DNS details to new root
        cmd.execute(
            f"cp /etc/resolv.conf {target_mountpoint}/etc/resolv.conf",
            dry_run=dry_run
        )

        # Temporarily override pacman initcpio hook so that it isn't run multiple times
        cmd.execute(
            f"mkdir -p {target_mountpoint}/etc/pacman.d/hooks",
            dry_run=dry_run
        )
        cmd.execute(
            f"touch {target_mountpoint}/etc/pacman.d/hooks/90-mkinitcpio-install.hook",
            dry_run=dry_run
        )

        self.target    = target_mountpoint
        self.dry_run   = dry_run
        self.installer = "pacman"
        self.efi_dir   = efi_directory

        self.system_groups     = self.__get_groups()

    #--------------------------------------------------------------------------

    def __enter__(self):
        return self

    #--------------------------------------------------------------------------

    def __wrap_chroot(
        self,
        command      : str,
        pipe_mode    : int  = 3,
        wait_for_proc: bool = True, 
        user         : str  = ""
    ):
        """Execute a command in the chroot environment

        Args:
            command (str): Command to be executed
            pipe_mode (int, optional): Octal code to specify which data streams to set to subprocess.PIPE. Defaults to 3.
            wait_for_proc (bool, optional): Whether or not to wait for the command to finish executing. Defaults to True.

        Returns:
            tuple: If wait_for_proc is True
            subprocess.Popen: If wait_for_proc is False
        """
        if user:
            full_command = f"chroot {self.target} su {user} -c '{command}'"
        else:
            full_command = f"chroot {self.target} sh -c '{command}'"

        return cmd.execute(
            full_command,
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

        initrd_conf = resub(
            rf'\nHOOKS=\(.*{preceding_hook}',
            rf'\g<0> {hook}',
            initrd_conf
        )

        with open(f"{self.target}/etc/mkinitcpio.conf", "w") as initrd_conf_file:
            initrd_conf_file.write(initrd_conf)

    #--------------------------------------------------------------------------
            
    def __add_kernel_parameter(self, parameter: str):
        with open(f"{self.target}/etc/kernel/cmdline", "a") as cmdline_file:
            cmdline_file.write(f"{parameter} ")
            
    def __get_kernel_parameters(self):
        with open(f"{self.target}/etc/kernel/cmdline", "r") as cmdline_file:
            kernel_cmdline = cmdline_file.read()
            
        return kernel_cmdline

    #--------------------------------------------------------------------------

    def __get_groups(self):
        groups = []
        with open(f"{self.target}/etc/group", "r") as groups_file:
            for groupline in groups_file.readlines():
                groups.append(groupline.split(":")[0])

        return groups

    #--------------------------------------------------------------------------

    def configure_clock(
        self,
        timezone    : str,
        hardware_utc: bool,
        enable_ntp  : bool
    ):

        # Create a symlink from the timezone file to /etc/localtime
        cmd.execute(
            f"ln -sf {self.target}/usr/share/zoneinfo/{timezone}" \
                + f"{self.target}/etc/localtime",
            dry_run=self.dry_run
        )

        # Configure the hardware clock to system time (with UTC if desired)
        self.__wrap_chroot(
            f"hwclock --systohc {'--utc' if hardware_utc else ''}"
        )

        # Enable systemd-timesyncd if desired
        if enable_ntp:
            self.__wrap_chroot("systemctl enable systemd-timesyncd")

    #--------------------------------------------------------------------------

    def configure_locales(
        self,
        locale_gen : list,
        locale_conf: str
    ):

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

    def set_hostname(self, hostname: str):
        with open(f"{self.target}/etc/hostname", "w") as hostname_file:
            hostname_file.write(hostname)

    #--------------------------------------------------------------------------

    def set_root_password(self, root_password: str):
        root_password_proc = self.__wrap_chroot(
            "passwd", 7, wait_for_proc=False
        )
        
        if not self.dry_run:
            root_password_proc.communicate(
                f"{root_password}\n{root_password}".encode()
            )

    #--------------------------------------------------------------------------

    def configure_user(
        self,
        username: str,
        shell   : str,
        home    : str,
        comment : str,
        groups  : list,
        sudo    : bool | str,
        password: str
    ):
        
        self.__wrap_chroot(
            f"useradd -m{f' -d {home}' if home else ''} {username}"
        )

        if shell:
            # Try to install shell if it does not exist
            with open(f"{self.target}/etc/shells", "r") as shells_file:

                shell_installed = False
                for shell_line in shells_file.readlines()[3:]:
                    if shell_line.strip() == shell:
                        shell_installed = True
                        break

                if not shell_installed:
                    self.__wrap_chroot(
                        f"pacman --noconfirm -S {shell.split('/')[-1]}"
                    )
                    
            self.__wrap_chroot(f"usermod -s {shell} {username}")

        # Add a comment if specified
        if comment:
            self.__wrap_chroot(f"usermod -c {comment} {username}")

        if groups:
            for group in groups:
                # Create group if it does not exist
                if group not in self.system_groups:
                    self.__wrap_chroot(f"groupadd {group}")
                    self.system_groups.append(group)
                
                # Add user to the group
                self.__wrap_chroot(f"usermod -a -G {group}, {username}")

        passwd_proc = self.__wrap_chroot(f"passwd {username}", 7, wait_for_proc=False)
        if not self.dry_run:
            passwd_proc.communicate(f"{password}\n{password}".encode())
            
        if sudo:
            if sudo == "nopass":
                sudo_user_conf = f"{username} ALL=(ALL:ALL) NOPASSWD: ALL"
            else:
                sudo_user_conf = f"{username} ALL=(ALL:ALL) ALL"
                
            with open(f"{self.target}/etc/sudoers.d/{username}", "w") as sudoers:
                sudoers.write(sudo_user_conf)

    #--------------------------------------------------------------------------

    def configure_early_crypt(self, encrypted_block: Formattable):
        self.__add_hook("block", "encrypt")

        self.__add_kernel_parameter(
            f"cryptdevice=UUID={encrypted_block.encrypt_uuid}:{encrypted_block.encrypt_label}"
        )

    #--------------------------------------------------------------------------

    def configure_late_crypt(self, encrypted_block: Formattable):
        crypttab_line = \
            f"{encrypted_block.encrypt_label}" \
                + f"\tUUID={encrypted_block.encrypt_uuid}"

        if encrypted_block.uses_keyfile:
            cmd.execute(
                f"cp /tmp/{encrypted_block.encrypt_label}.key " \
                    + f"{self.target}/etc/cryptsetup-keys.d/"
            )
            crypttab_line += \
                f"\t/etc/cryptsetup-keys.d/{encrypted_block.encrypt_label}.key\n"

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
        self.__wrap_chroot("useradd -N -m aurbuilder")

        # Create a drop in sudo configuration file for the temporary user
        with open(f"{self.target}/etc/sudoers.d/aurbuilder", "w") as sudoers:
            sudoers.write("aurbuilder ALL=(ALL:ALL) NOPASSWD: ALL")
        
        # Download git and clone the AUR helper repo
        self.__wrap_chroot("pacman --noconfirm -S git")
        self.__wrap_chroot(f"git clone {helper_url} ~/{helper}", user="aurbuilder")

        # Build and install the helper
        self.__wrap_chroot(f"cd ~/{helper} && makepkg -S", user="aurbuilder")
        self.__wrap_chroot(f"cd ~/{helper} && makepkg --noconfirm -i", user="aurbuilder")

    #--------------------------------------------------------------------------

    def install_packages(self, packages: list):
        if self.installer == "pacman":
            self.__wrap_chroot(f"pacman --noconfirm -Syu {' '.join(packages)}")
        else:
            self.__wrap_chroot(
                f"{self.installer.strip('-bin')} --noconfirm -Syu {' '.join(packages)}",
                user="aurbuilder"
            )

    #--------------------------------------------------------------------------

    def enable_services(self, services: list):
        for service in services:
            self.__wrap_chroot(f"systemctl enable {service}")
            
    #--------------------------------------------------------------------------
    
    def set_default_kernel_params(
        self,
        root_uuid: str,
        root_subvol: str
    ):
        
        # Specify the root uuid
        cmdline = f"root=UUID={root_uuid}"
        
        # Specify the BTRFS root subvolume if applicable
        if root_subvol:
            cmdline += f" rootflags=subvol={root_subvol}"
            
        self.__add_kernel_parameter(cmdline)
        
    #--------------------------------------------------------------------------
        
    def generate_ukis(self):
        presets_dir = f"{self.target}/etc/mkinitcpio.d/"
        
        cmd.execute(f"mkdir -p {self.efi_dir}/EFI/Linux", dry_run=self.dry_run)
        
        self.generate_initramfs()
        
        for preset in listdir(presets_dir):
            with open(presets_dir+preset, "r") as preset_file:
                preset_config = preset_file.read()
                
            # Uncomment default and fallback UKI lines in preset and set the efi directory
            preset_config = resub(
                r'\n#(default_uki=")/efi',
                rf'\n\g<1>{self.efi_dir}',
                preset_config
            )
            
            preset_config = resub(
                r'\n#(fallback_uki=")/efi',
                rf'\n\g<1>{self.efi_dir}',
                preset_config
            )
            
            # Comment out the initramfs default and fallback image lines
            preset_config = resub(
                r'\n(default_image)',
                r'\n#\g<1>',
                preset_config
            )
            
            preset_config = resub(
                r'\n(fallback_image)',
                r'\n#\g<1>',
                preset_config
            )
            
            with open(presets_dir+preset, "w") as preset_file:
                preset_file.write(preset_config)

    #--------------------------------------------------------------------------

    def configure_grub(self):
        with open(f"{self.target}/etc/default/grub", "r") as grub_file:
            grub_config = grub_file.read()

        kernel_cmdline = self.__get_kernel_parameters()

        grub_config = resub(
            r'\nGRUB_CMDLINE_LINUX_DEFAULT="',
            rf'\g<0>{kernel_cmdline}',
            grub_config
        )

        with open(f"{self.target}/etc/default/grub", "w") as grub_file:
            grub_file.write(grub_config)
            
        self.__wrap_chroot(
            "grub-install --target=x86_64-efi " \
                + f"--efi-directory={self.efi_dir} --bootloader-id=GRUB"
        )

        self.__wrap_chroot(
            "grub-mkconfig -o /boot/grub/grub.cfg"
        )
        
    #--------------------------------------------------------------------------
    
    def configure_efistub(
        self,
        disk: str,
        partition: int,
        boot_label: str,
        kernel: str
    ):
        
        efibootmgr_command = "efibootmgr --create"
        
        # Add the disk and partition arguments
        efibootmgr_command += f" --disk {disk} --part {partition}"
        
        # Add the label that will show up as a boot entry
        efibootmgr_command += f" --label \"{boot_label}\""
        
        # Add the path to the efi executable
        efi_executable = f"arch-linux{f'-{kernel}' if kernel else ''}.efi"
        
        efibootmgr_command += f" --loader '/EFI/Linux/{efi_executable}"
        
        # Add the unicode argument
        efibootmgr_command += " --unicode"
        
        self.__wrap_chroot(efibootmgr_command)
        
    #--------------------------------------------------------------------------
    
    def generate_fstab(self):
        mounts = cmd.execute(f"genfstab -U {self.target}", 6, self.dry_run)[0]
        
        with open(f"{self.target}/etc/fstab", "a") as fstab_file:
            fstab_file.write(mounts)
            
    #--------------------------------------------------------------------------

    def exit(self):
        # Clean up aur helper user if needed
        if self.installer != "pacman":
            self.__wrap_chroot("userdel aurbuilder")
            self.__wrap_chroot("rm /etc/sudoers.d/aurbuilder")
            
        cmd.execute(
            f"rm {self.target}/etc/pacman.d/hooks/90-mkinitcpio-install.hook",
            dry_run=self.dry_run
        )

        # Unmount all API filesystems from new root
        cmd.execute(f"umount -R {self.target}/proc/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/sys/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/dev/", dry_run=self.dry_run)
        cmd.execute(f"umount -R {self.target}/run/", dry_run=self.dry_run)

    #--------------------------------------------------------------------------

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit()


