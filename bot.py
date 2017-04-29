import json
import time
import asyncio
import logging.config
from contextlib import suppress
from datetime import datetime
from operator import itemgetter
from itertools import islice

import discord
from aionationstates import NationControl


with open('config.json') as f:
    config = json.load(f)

with suppress(KeyError):
    logging.config.dictConfig(config['LOGGING'])

logger = logging.getLogger('discord-plays-nationstates')
client = discord.Client()


@client.event
async def on_ready():
    logger.info(f'Logged in as {client.user.name} ({client.user.id})')


inconsistency_message = '''\
There seems to be an inconsistency between the issues confronting {} and the \
messages in this channel.
Either someone's been answering issues on their own or deleting bot's messages.
Or maybe there is an error in the code.

No issue answered, opening the vote for a new one...'''

new_issue_message = 


number_to_emoji = {
    1: ':one:',
    2: ':two:',
    3: ':three:',
    4: ':four:',
    5: ':five:',
    6: ':six:',
    7: ':seven:',
    8: ':eight:',
    9: ':nine:',
    10: ':ten:'
}
emoji_to_number = dict(reversed(i) for i in number_to_emoji.items())


def census(census_before, census_after):
    def percentages():
        for before, after in zip(census_before, census_after):
            title = before.info.title
            before = before.score or 0.001
            after = after.score or 0.001
            yield title, ((after - before) / before) * 100
    
    return (
        f'{title:<35} {percentage:.2f}%'
        for title, percentage
        in sorted(
            islice(
                sorted(
                    percentages(),
                    key=lambda x: abs(x[1]),
                    reverse=True
                ),
                11
            ),
            key=itemgetter(1),
            reverse=True
        )
    )


async def close_issue(issue_channel, issue, option):
    census_before = await s.shard('census')
    await option.accept()
    census_after = await s.shard('census')
    embed = discord.Embed(
        title=issue.title,
        description=issue.text,
        colour=discord.Colour(0xde3831),
        timestamp=datetime.now()
    )
    embed.add_field(
        name=':white_check_mark::',
        value=option.text
    )
    embed.add_field(
        name=':chart_with_upwards_trend::',
        value=option.text
    )
    await client.send_message('Legislation Passed:', embed=embed)

async def open_issue(issue_channel, issue, flag, inform_channel):
    embed = discord.Embed(
        title=issue.title,
        description=issue.text,
        colour=discord.Colour(0xfdc82f),
        timestamp=datetime.now()
    )

    # TODO this
    #embed.set_image(url=)
    embed.set_thumbnail(url=flag)

    for i, option in enumerate(issue.options):
        embed.add_field(
            name=number_to_emoji[i] + ':',
            value=option.text
        )

    message = await client.send_message(f'Issue #{issue.id}:', embed=embed)
    for i in range(len(options)):
        await client.add_reaction(message, number_to_emoji[i])
    await client.send_message(
        inform_channel,
        f'New issue: **{issues[1]}**\n'
        f'Head over to {issue_channel.mention} for more.'
    )

def vote_results(message, issue):
    for i, (reaction, option) in enumerate(zip(message.reactions,
                                               issue.options)):
        print(reaction.emoji)
        assert emoji_to_number(reaction.emoji) == i
        yield option, reaction.count


async def issue_cycle(nation, issues_channel, inform_channel):
    s = await nation.shards('issues', 'flag')
    issues = s['issues']
    
    async for message in client.logs_from(issues_channel, limit=50):
        if (message.author == client.user and
                message.content.startswith('Issue #')):
            if not message.content.startswith(f'Issue #{issue.id}:'):
                logger.warn(f'message issue discrepancy for {nation.name}')
                client.send_message(issues_channel,
                                    inconsistency_message.format(nation.name))
                await open_issue(issue_channel, issues[0], flag)
                return
            option, _ = max(vote_results(message, issues[0]), key=itemgetter(1))
            await close_issue(issue_channel, issues[0], option)
            logger.info(f'close issue {issues[0].id} for {nation.name}')
            await open_issue(issue_channel, issues[1], flag)
            logger.info(f'open issue {issues[1].id} for {nation.name}')
            await client.send_message(
                inform_channel,
                new_issue_message.format(issues[1], issue_channel.mention)
            )
            return
    logger.info(f'open first issue {issues[1].id} for {nation.name}')
    await open_issue(issue_channel, issues[1], flag)

    return
    
    await client.send_message(channel, counter)
    


async def issue_cycle_loop(server):
    await client.wait_until_ready()
    
    issues_channel = client.get_channel(server['ISSUES_CHANNEL'])
    inform_channel = client.get_channel(server['INFORM_CHANNEL'])
    
    nation = NationControl(server['NATION'], autologin=server['AUTOLOGIN'])
    while not client.is_closed:
        logger.info(f'started cycle for {nation.name}')
        started_at = time.time()
        
        await issue_cycle(nation, issues_channel, inform_channel)
        
        finished_at = time.time()
        delta = finished_at - started_at
        await asyncio.sleep(server['ISSUE_PERIOD'] - delta)


for server in config['SERVERS']:
    client.loop.create_task(issue_cycle(server))


if __name__ == "__main__":
    client.run(config['DISCORD_API_KEY'])
