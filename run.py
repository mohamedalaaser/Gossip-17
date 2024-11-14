"""Run the gossip application."""

from argparse import ArgumentParser
import asyncio
import os
from gossip.gossip import Gossip


async def main():
    """Main entry point for the whole application."""
    print("program started")
    # Parse command-line arguments

    config_file_path = "config.ini"
    env_config_file_path = os.getenv("conf")
    if env_config_file_path is not None:
        config_file_path = env_config_file_path
    else:
        parser = ArgumentParser()
        parser.add_argument(
            "-c",
            "--config",
            help="Path to the configuration file",
            default="config.ini",
            metavar="",
        )
        args = parser.parse_args()

        config_file_path = args.config

    await Gossip(config_file_path).run()


if __name__ == "__main__":
    asyncio.run(main())
