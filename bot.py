import json
import time
import random
import asyncio
import traceback
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


def html_to_md(html):
    return (
        html
        .replace('<i>', '*')
        .replace('</i>', '*')
        .replace('&quot;', '"')
    )


number_to_emoji = {
    0: '1⃣',
    1: '2⃣',
    2: '3⃣',
    3: '4⃣',
    4: '5⃣',
    5: '6⃣',
    6: '7⃣',
    7: '8⃣',
    8: '9⃣',
    9: '🔟'
}
emoji_to_number = dict(reversed(i) for i in number_to_emoji.items())


def census_difference(census_change):
    mapping = (
        sorted(
            islice(
                sorted(
                    (
                        (scale.info.title, scale.pchange)
                        for scale in census_change
                    ),
                    key=lambda x: abs(x[1]),
                    reverse=True
                ),
                11
            ),
            key=itemgetter(1),
            reverse=True
        )
    )
    
    for title, percentage in mapping:
        highlight = arrow = ' '
        if percentage > 0:
            highlight = '+'
            arrow = '↑'
        elif percentage < 0:
            highlight = '-'
            arrow = '↓'
        percentage = abs(percentage)
        yield f'{highlight}{title:<35} {arrow}{percentage:.2f}%'


async def close_issue(issue_channel, nation, issue, option):
    issue_result = await option.accept()
    logger.info(f'answer issue {issue.id} for {nation.id}')
    embed = discord.Embed(
        title=issue.title,
        description=html_to_md(issue.text),
        colour=discord.Colour(0xde3831),
        timestamp=datetime.utcnow()
    )
    embed.add_field(
        name=':white_check_mark::',
        inline=False,
        value=html_to_md(option.text)
    )
    if issue_result.desc:
        embed.add_field(
            name=':pencil::',
            inline=False,
            value=html_to_md(issue_result.desc.capitalize() + '.')
        )
    if issue_result.headlines:
        embed.add_field(
            name=':newspaper::',
            inline=False,
            value=(
                ';\n'
                .join((
                    html_to_md(headline)
                    for headline in issue_result.headlines
                ))
            )
        )
    if issue_result.rankings:
        embed.add_field(
            name=':chart_with_upwards_trend::',
            inline=False,
            value=(
                '```diff\n{}\n```'
                .format('\n'.join(census_difference(issue_result.rankings)))
            )
        )
    for banner in issue_result.unlocks:
            await client.send_message(issue_channel,
                                      f'New banner unlocked: {banner}')
    await client.send_message(
        issue_channel,
        'Legislation Passed:',
        embed=embed
    )
    print(
        issue_result.unlocks,
        
    )

async def open_issue(issue_channel, issue, flag, inform_channel):
    embed = discord.Embed(
        title=issue.title,
        description=html_to_md(issue.text),
        colour=discord.Colour(0xfdc82f),
        timestamp=datetime.utcnow()
    )

    print(issue.banners)
    if issue.banners:
        embed.set_image(url=issue.banners[0])

    embed.set_thumbnail(url=flag)

    for i, option in enumerate(issue.options):
        embed.add_field(
            name=number_to_emoji[i] + ':',
            value=html_to_md(option.text)
        )

    message = await client.send_message(
        issue_channel,
        f'Issue #{issue.id}:',
        embed=embed
    )
    for i in range(len(issue.options)):
        await client.add_reaction(message, number_to_emoji[i])
    await client.send_message(
        inform_channel,
        f'New issue: **{issue.title}**\n'
        f'Head over to {issue_channel.mention} for more.'
    )

def vote_results(message, issue):
    for i, (reaction, option) in enumerate(zip(message.reactions,
                                               issue.options)):
        assert reaction.emoji == number_to_emoji[i]
        yield option, reaction.count


async def get_last_issue_message(issue_channel):
    async for message in client.logs_from(issue_channel, limit=50):
        if (message.author == client.user and
                message.content.startswith('Issue #')):
            return message

async def issue_cycle(nation, issue_channel, inform_channel):
    issues, flag = await (nation.issues() + nation.flag())
    issues = list(reversed(issues))
    
    last_issue_message = await get_last_issue_message(issue_channel)
    if (last_issue_message and
            last_issue_message.content == f'Issue #{issues[0].id}:'):
        results = list(vote_results(last_issue_message, issues[0]))
        _, max_votes = max(results, key=itemgetter(1))
        option = random.choice(
            [option for option, votes in results if votes == max_votes])

        await close_issue(issue_channel, nation, issues[0], option)
        logger.info(f'close issue {issues[0].id} for {nation.id}')
        await open_issue(issue_channel, issues[1], flag, inform_channel)
        logger.info(f'open next issue {issues[1].id} for {nation.id}')
    else:
        await open_issue(issue_channel, issues[0], flag, inform_channel)
        logger.info(f'open first issue {issues[0].id} for {nation.id}')


async def issue_cycle_loop(server):
    await client.wait_until_ready()
    
    issue_channel = client.get_channel(server['ISSUES_CHANNEL'])
    inform_channel = client.get_channel(server['INFORM_CHANNEL'])

    nation = NationControl(
        server['NATION'],
        autologin=server.get('AUTOLOGIN') or '',
        password=server.get('PASSWORD') or ''
    )

    await client.change_presence(game=discord.Game(name='NationStates'))
    await client.edit_profile(username=await nation.name())

    now = datetime.utcnow()
    today_seconds = (
        now.timestamp()
        - now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    )
    to_sleep = server['ISSUE_PERIOD'] - today_seconds % server['ISSUE_PERIOD']
    logger.info(f'sleeping {to_sleep} seconds before starting the'
                f' issue cycle loop for {nation.id}')
    await asyncio.sleep(to_sleep)

    while not client.is_closed:
        logger.info(f'start cycle for {nation.id}')
        started_at = time.time()
        
        try:
            await issue_cycle(nation, issue_channel, inform_channel)
        except:
            logger.error(f'for {nation.id}:\n' + traceback.format_exc())
        
        logger.info(f'end cycle for {nation.id}')
        finished_at = time.time()
        delta = finished_at - started_at
        await asyncio.sleep(server['ISSUE_PERIOD'] - delta)


for server in config['SERVERS']:
    client.loop.create_task(issue_cycle_loop(server))


if __name__ == "__main__":
    client.run(config['DISCORD_API_KEY'])
