# Standard
import functools
import traceback
import logging.config

# External
import aionationstates
import discord.ext.commands as discord_cmds

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
bot = discord_cmds.Bot(command_prefix='.')

def main():
    import configparser
    import pathlib
    config = configparser.ConfigParser()
    config.read(pathlib.Path(__file__).parent / 'play_nationstates.ini')

    aionationstates.set_user_agent(config['Bot']['useragent'])

    bot.load_extension('core')
    core = bot.extensions['core']
    config_channel = int(config['GuildNation']['channel'])
    offset = float(config['GuildNation']['utc_start'])
    issues = int(config['GuildNation']['daily_issues'])

    @bot.event
    @call_once
    async def on_ready():
        channel = bot.get_channel(config_channel)
        assert channel is not None, f'Parsed int {config_channel} did not match channel.'
        nation = aionationstates.NationControl(config['GuildNation']['nation'], password=config['GuildNation']['password'])
        app = await bot.application_info()
        core.instantiate(nation, channel, app.owner.id, issues_per_day=issues, first_issue_offset=offset)

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, discord_cmds.CommandNotFound):
            return

        if isinstance(error, discord_cmds.CommandInvokeError):
            error_str = (
                f'In {ctx.command.qualified_name}:\n'
                + ''.join(traceback.format_tb(error.original.__traceback__))
                + '{0.__class__.__name__}: {0}'.format(error.original))
            logger.error(error_str)

    bot.run(config['Bot']['token'])

def _main():
    import argparse
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

    parser.add_argument(
        '--issues',
        type=int,
        required=False,
        default=4,
        choices=range(1, 5),
        help='Number of issues to request per day.')
    parser.add_argument(
        '--offset',
        type=float,
        required=False,
        default=0,
        help='Hours after midnight to post first issue of the day.')

    args = parser.parse_args()


    # Sample setup:

    aionationstates.set_user_agent(args.useragent)

    bot.load_extension('core')
    core = bot.extensions['core']


    @bot.event
    @call_once
    async def on_ready():
        channel = bot.get_channel(args.channel)
        nation = aionationstates.NationControl(args.nation, password=args.password)
        assert channel is not None
        app = await bot.application_info()
        core.instantiate(
            nation, channel, app.owner.id,
            issues_per_day=args.issues,
            first_issue_offset=args.offset)


    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, discord_cmds.CommandNotFound):
            return

        if isinstance(error, discord_cmds.CommandInvokeError):
            error_str = (
                f'In {ctx.command.qualified_name}:\n'
                + ''.join(traceback.format_tb(error.original.__traceback__))
                + '{0.__class__.__name__}: {0}'.format(error.original))
            logger.error(error_str)

    bot.run(args.token)

def call_once(func):
    called_already = False

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        nonlocal called_already
        if not called_already:
            called_already = True
            return await func(*args, **kwargs)
    return wrapper

if __name__ == "__main__":
    _main()
