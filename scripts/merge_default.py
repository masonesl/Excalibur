from enum import Enum


class Defaults(Enum):

    PARENT = {
        "drives" : {},
        "raid" : {},
        "crypt": {},
        "filesystems" : {},
        "clock" : {},
        "locales" : {},
        "hostname" : "myhostname"
    }

    DRIVE = {
        "device-path" : None,
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

    FILESYSTEM = {
        "filesystem": None,
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


def fill_defaults(config: dict, default_config: Defaults) -> dict:
    default_config = default_config.value

    for option in default_config:
        if option not in config:
            config[option] = default_config[option]
    
    return config

# EOF