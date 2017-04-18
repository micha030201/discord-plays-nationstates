import json
import logging.config
from contextlib import suppress

import discord


with open('config.json') as f:
    config = json.load(f)

with suppress(KeyError):
    logging.config.dictConfig(config['LOGGING'])

logger = logging.getLogger('discord-plays-nationstates')
client = discord.Client()


@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user.name} ({client.user.id})')


if __name__ == "__main__":
    client.run(config['DISCORD_API_KEY'])
