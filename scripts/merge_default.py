from enum import Enum


class Defaults(Enum):

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


def merge(config: dict, default_config: Defaults):
    default_config = default_config.value

    for option in default_config:
        if option not in config:
            config[option] = default_config[option]

    return config

# EOF