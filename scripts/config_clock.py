from subprocess import run
# import yaml

command_output = []

TIMEZONE = "America/Denver"

def main():
    # Set the time zone
    command_output.append(run(["ln", "-sf", f"/usr/share/zoneinfo/{TIMEZONE}", "/etc/localtime"]))

    # Set the hardware clock from the system clock
    command_output.append(run(["hwclock", "--systohc", "--utc"]))

    # Enable NTP synchronization
    command_output.append(run(["systemctl", "enable", "systemd-timesyncd"]))


