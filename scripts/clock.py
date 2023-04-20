import subprocess


def configure(timezone: str=None,
              hardware_utc: bool=True,
              enable_ntp: bool=True):

    if timezone:
        # Command to symlink timezone to localtime
        timezone_command = ["ln", "-sf",
                            f"/usr/share/zoneinfo/{timezone}",
                            "/etc/localtime"]

        # print(subprocess.run(timezone_command))
        print(" ".join(timezone_command))

    hwclock_command = ["hwclock", "--systohc"]

    if hardware_utc:
        hwclock_command.append("--utc")
    
    # print(subprocess.run(hwclock_command))
    print(" ".join(hwclock_command))

    if enable_ntp:
        ntp_enable_command = ["systemctl", "enable", "systemd-timesyncd"]

        # print(subprocess.run(ntp_enable_command))
        print(" ".join(ntp_enable_command))