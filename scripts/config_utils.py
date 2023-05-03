from enum import Enum
from yaml import safe_load

#------------------------------------------------------------------------------

class Required:
    """A placeholder class to give to an option that is required to continue
    """
    pass

#------------------------------------------------------------------------------

class Defaults(Enum):

    PARENT = {
        "drives" : {},
        "raid" : {},
        "crypt": {},
        "filesystems" : {},
        "clock" : {},
        "locales" : {},
        "hostname" : "myhostname",
        "aur-helper" : None,
        "packages" : [],
        "services" : []
    }

    DRIVE = {
        "device-path" : Required(),
        "gpt" : True,
        "partitions" : {}
    }

    PARTITION = {
        "size" : "0",
        "start-sector" : "0",
        "end-sector" : "0",
        "type-code" : "8300",
        "partition-label" : None
    }

    RAID = {
        "devices" : Required(),
        "array-name" : Required(),
        "level" : Required()
    }

    CRYPT = {
        "crypt-label" : Required(),
        "load-early" : False,
        "generate-keyfile" : False,
        "password" : "password"
    }

    FILESYSTEM = {
        "filesystem": Required(),
        "label": None,
        "mountpoint": None
    }

    CLOCK = {
        "timezone": "UTC",
        "hardware-utc": True,
        "enable-ntp": True
    }

    LOCALES = {
        "locale-gen" : [
            "en_US.UTF-8 UTF-8"
        ],
        "locale-conf" : "en_US.UTF-8"
    }

    USER = {
        "shell" : "/bin/bash",
        "home"  : "",
        "comment" : "",
        "groups" : [],
        "password" : "password"
    }

#------------------------------------------------------------------------------

class Config:

    def __init__(self, config_file_path: str):
        with open(config_file_path, "r") as config_file:
            config = safe_load(config_file)

        config = self.fill_defaults(config, Defaults.PARENT)

        self.missing_required  = []
        self.password_warnings = {
            "users"      : [],
            "encryption" : []
        }
        
        self.drives      = {}
        for drive in config["drives"]:
            drive_config = config["drives"][drive]

            self.drives[drive] = self.fill_defaults(
                drive_config,
                Defaults.DRIVE,
                ["drives", drive]
            )

            for partition in drive_config["partitions"]:
                partition_config = drive_config["partitions"][partition]

                self.drives[drive]["partitions"][partition] = self.fill_defaults(
                    partition_config,
                    Defaults.PARTITION,
                    ["drives", drive, "partitions", partition]
                )
    
        self.raid = {}
        for array in config["raid"]:
            raid_config = config["raid"][array]

            self.raid[array] = self.fill_defaults(
                raid_config,
                Defaults.RAID,
                ["raid", array]
            )

        self.crypt = {}
        for crypt_dev in config["crypt"]:
            crypt_config = config["crypt"][crypt_dev]

            if "password" in crypt_config:
                self.password_warnings["encryption"].append(crypt_dev)

            self.crypt[crypt_dev] = self.fill_defaults(
                crypt_config,
                Defaults.CRYPT,
                ["crypt", crypt_dev]
            )

        self.filesystems = {}
        for device in config["filesystems"]:
            filesystem_config = config["filesystems"][device]

            self.filesystems[device] = self.fill_defaults(
                filesystem_config,
                Defaults.FILESYSTEM,
                ["filesystems", device]
            )

        self.clock = self.fill_defaults(
            config["clock"],
            Defaults.CLOCK,
            ["clock"]
        )

        self.locales = self.fill_defaults(
            config["locales"],
            Defaults.LOCALES,
            ["locales"]
        )

        self.hostname = config["hostname"]

        self.users = {}
        for user in config["users"]:
            user_config = config["users"][user]

            if "password" in user_config:
                self.password_warnings["users"].append(user)

            self.users[user] = self.fill_defaults(
                user_config,
                Defaults.USER,
                ["users", user]
            )

        self.aur_helper = config["aur-helper"]
        self.packages   = config["packages"]
        self.services   = config["services"]

    def fill_defaults(self, config: dict,
                            default_config: Defaults,
                            key_path: list=None) -> dict:

        default_options = default_config.value

        for option in default_options:
            if option not in config:
                if type(default_options[option]) == Required:
                    self.missing_required.append(key_path+[option])
                else:
                    config[option] = default_options[option]

        return config
# EOF