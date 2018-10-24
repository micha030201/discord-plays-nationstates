import argparse
import traceback
import logging.config

from discord.ext import commands
import aionationstates

import utils
import core


def main():
    parser = argparse.ArgumentParser()
    required = parser.add_argument_group('required arguments')

    required.add_argument(
        '--token',
        help='The token for your Discord bot',
        required=True
        )
    required.add_argument(
        '--useragent',
        help='User-Agent header for the NationStates API',
        required=True
        )
    required.add_argument(
        '--nation',
        help='Name of the nation you want to answer issues of',
        required=True
        )
    required.add_argument(
        '--password',
        help='Password to the nation',
        required=True
        )
    required.add_argument(
        '--channel',
        help='ID of the Discord channel to use',
        type=int,
        required=True
        )

    optional = parser.add_argument_group('optional arguments')
    optional.add_argument(
        '--offset', type=float, required=False,
        help='Hours after midnight to post first issue of the day.')

    args = parser.parse_args()


    # Sample setup:

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(filename)s: %(message)s"
                }
            },
        "handlers": {
            "to_console": {
                "level": "DEBUG",
                "formatter": "standard",
                "class": "logging.StreamHandler"
                }
            },
        "loggers": {
            "discord": {
                "handlers": ["to_console"],
                "level": "INFO",
                "propagate": False
                },
            "aionationstates": {
                "handlers": ["to_console"],
                "level": "DEBUG",
                "propagate": False
                },
            "discord-plays-nationstates": {
                "handlers": ["to_console"],
                "level": "DEBUG",
                "propagate": False
                }
            }
        })

    logger = logging.getLogger('discord-plays-nationstates')

    aionationstates.set_user_agent(args.useragent)

    bot = commands.Bot(command_prefix='.')

    bot.load_extension('core')


    @bot.event
    @utils.call_once
    async def on_ready():
        channel = bot.get_channel(args.channel)
        nation = aionationstates.NationControl(args.nation, password=args.password)
        assert channel is not None
        core.instantiate(nation, channel, first_issue_offset=args.offset or 0)


    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.CommandInvokeError):
            error_str = (
                f'In {ctx.command.qualified_name}:\n'
                + ''.join(traceback.format_tb(error.original.__traceback__))
                + '{0.__class__.__name__}: {0}'.format(error.original))
            logger.error(error_str)

    bot.run(args.token)
