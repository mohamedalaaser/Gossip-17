"""hanldes parsing the config.ini file and validating it and provides the Config class"""

from configparser import ConfigParser
import re


def is_valid_filepath(value):
    """Regex for file path validation"""
    hostkey_regex = re.compile(r"^/?(.+/)?[^/]+\.pem$")
    return hostkey_regex.match(value) is not None


def is_valid_ip_port(value):
    """Regex for IP:port validation"""
    ip_port_regex = re.compile(
        r"^(?:(?:[0-9]{1,3}\.){3}[0-9]{1,3}|\w+\.\w+(\.\w+)*):[0-9]{1,5}$"
    )
    return ip_port_regex.match(value) is not None


def is_valid_challenge_difficulty(value):
    value = int(value)
    return value >= 0 and value <= 64


class Config:
    """Config class to hold config values"""

    configFileDetails = {
        "global": {
            "hostkey": [is_valid_filepath],
        },
        "gossip": {
            "cache_size": [int],
            "degree": [int],
            "bootstrapper": [is_valid_ip_port],
            "p2p_address": [is_valid_ip_port],
            "api_address": [is_valid_ip_port],
            "challenge_timeout": [int],
            "challenge_difficulty": [is_valid_challenge_difficulty, int],
            "discovery_cooldown": [int],
        },
    }

    def __init__(self, config_file_path):
        print("=====================================")
        print(f"Reading config file from {config_file_path}")
        config = ConfigParser()
        config.read(config_file_path)
        self.__validate_config_file(config)
        print(">>>> config file read and validated successfully <<<<")
        print(vars(self))
        print("=====================================")

    def __validate_config_file(self, config: ConfigParser):
        """Validate the config file"""
        for section, options in self.configFileDetails.items():
            if not config.has_section(section):
                raise ValueError(f"Section '{section}' is missing in the config file")

            for option, validations in options.items():
                if not config.has_option(section, option):
                    raise ValueError(
                        f"Key '{option}' is missing in the '{section}' section"
                    )

                value = config.get(section, option)

                try:
                    for validation in validations:
                        if validation == int:
                            int(value)
                            value = int(value)
                        elif not validation(value):
                            raise ValueError()
                except ValueError as e:
                    raise ValueError(
                        f"Invalid value for '{option}' in section '{section}'. "
                    ) from e
                setattr(self, option, value)
                print(f"Setting {option} to {value}")
