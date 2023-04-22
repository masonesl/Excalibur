import subprocess
from shlex import split as shsplit

class Chroot:

    def __init__(self, target_mountpoint: str="/mnt"):
        # Start an arch-chroot process to mount everything correctly
        # Running commands on the new root won't be done through arch-chroot
        # Each command ran will be run with its own chroot subprocess
        # This probably isn't the best way to do it so it might be changed later
        # self.arch_chroot_process = subprocess.Popen(
        #     ["arch-chroot", target_mountpoint],
        #     stdout=subprocess.PIPE,
        #     stderr=subprocess.PIPE,
        #     stdin=subprocess.PIPE
        # )
        print("started arch-chroot")

        self.chroot_template = ["chroot", target_mountpoint]
        self.target = target_mountpoint

    def __enter__(self):
        return self

    def __create_chroot(self, *args) -> subprocess.Popen:
        return subprocess.Popen(self.chroot_template+(args if args else []), 
                                stdin=subprocess.PIPE,
                                stderr=subprocess.PIPE)

    def __wrap_chroot(self, command):
        # return subprocess.Popen(shsplit(f"chroot {self.target} "+command),
        #                                           stdin=subprocess.PIPE,
        #                                           stderr=subprocess.PIPE)
        print(f"chroot {self.target} "+command)

    def configure_clock(self, timezone: str="",
                              hardware_utc: bool=True,
                              enable_ntp: bool=True):

        target = self.target # For readability

        # Create a symlink from the timezone file to /etc/localtime
        if timezone:
            timezone_command = \
                f"ln -sf {target}/usr/share/zoneinfo/{timezone} {target}/etc/localtime"
            # subprocess.run(shsplit(timezone_command), stderr=subprocess.PIPE)
            print(timezone_command)

        # Configure the hardware clock to system time (with UTC if desired)
        hardware_clock_command = f"hwclock --systohc {'--utc' if hardware_utc else ''}"
        self.__wrap_chroot(hardware_clock_command)

        # Enable systemd-timesyncd if desired
        if enable_ntp:
            enable_ntp_command = "systemctl enable systemd-timesyncd"
            self.__wrap_chroot(enable_ntp_command)

    def configure_locales(self, locale_gen: list=["en_US.UTF-8 UTF-8"],
                                locale_conf: str="en_US.UTF-8"):
        
        target = self.target

        # Create a chroot process for locale configuration
        # locale_chroot = self.__create_chroot()
        locale_config_command = []

        # Uncomment each specified locale in /etc/locale.gen
        for locale in locale_gen:
            uncomment_locale = f"sed -i s/#{locale}/{locale}/g {target}/etc/locale.gen"
            # subprocess.Popen(shsplit(uncomment_locale))
            print(uncomment_locale)

        # Generate locales
        self.__wrap_chroot("locale-gen")

        # Set the LANG variable to desired locale
        locale_config_command.append(f"echo LANG={locale_conf} > /etc/locale.conf")

        # locale_chroot.communicate(input="\n".join(locale_config_command).encode())
        print("\n".join(locale_config_command).encode())

    def configure_host(self, hostname: str="myhostname"):
        # Create a chroot process for host configuration
        # host_chroot = self.__create_chroot()

        host_config_command = []

        # Set the hostname
        host_config_command.append(f"echo {hostname} > /etc/hostname")

        # /etc/hosts configuration section
        host_config_command.append("echo 127.0.0.1\tlocalhost >> /etc/hosts")
        host_config_command.append("echo ::1\tlocalhost >> /etc/hosts")

        # host_chroot.communicate(input="\n".join(host_config_command).encode())
        print("\n".join(host_config_command))

    def configure_users(self, root_password: str="",
                              users: dict={}):
        
        # Set the root password
        root_passwd_chroot = self.__create_chroot("passwd")
        root_passwd_chroot.communicate(input=f"{root_password}\n{root_password}".encode())
        
        for username in users:
            useradd_command = ["useradd", "-m", "-G"] + users[username]["groups"]

            useradd_command.append("")

    def __exit__(self, exc_type, exc_value, traceback):
        # self.arch_chroot_process.communicate(b"exit")
        print("exited arch-chroot")


