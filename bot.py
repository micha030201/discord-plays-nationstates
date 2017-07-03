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
import aionationstates


logger = logging.getLogger('discord-plays-nationstates')


def html_to_md(html):
    return (
        html
        .replace('*', '\*')
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


def vote_results(message, issue):
    for i, (reaction, option) in enumerate(zip(message.reactions,
                                               issue.options)):
        assert reaction.emoji == number_to_emoji[i]
        yield option, reaction.count


class DPNInstance:
    def __init__(self, *, api_key, issue_channel, inform_channel,
                 nation, issue_period, first_issue_offset):
        self.issue_channel = issue_channel
        self.inform_channel = inform_channel
        self.nation = nation
        self.issue_period = issue_period
        self.first_issue_offset = first_issue_offset
        self.client = discord.Client()
        self.client.event(self.on_message)
        asyncio.ensure_future(self.client.start(api_key))
        self.issue_cycle_loop_task = \
            asyncio.ensure_future(self.issue_cycle_loop())

    async def on_message(self, message):
        if not message.content == self.client.user.mention:
            return
        description = await self.nation.description()
        message = await self.client.send_message(
            message.channel,
            f'https://nationstates.net/{self.nation.id}\n\n{description}'
        )

    async def close_issue(self, issue, option):
        issue_result = await option.accept()
        logger.info(f'answer issue {issue.id} for {self.nation.id}')
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
        if issue_result.happening:

            reclass_lines = []
            r = issue_result.reclassifications
            if r.govt:
                reclass_lines.append(
                    f'Reclassified from *{r.govt.before}* to *{r.govt.after}*')
            if r.civilrights:
                reclass_lines.append(
                    f'Civil Rights changed from *{r.civilrights.before}*'
                    f' to *{r.civilrights.after}*')
            if r.economy:
                reclass_lines.append(
                    f'Economy changed from *{r.economy.before}*'
                    f' to *{r.economy.after}*')
            if r.politicalfreedom:
                reclass_lines.append(
                    f'Political Freedom changed from *{r.politicalfreedom.before}*'
                    f' to *{r.politicalfreedom.after}*')
            reclass_lines = ';\n'.join(reclass_lines)
            reclassifications = \
                f'\n\n**{reclass_lines}.**' if reclass_lines else ''

            embed.add_field(
                name=':pencil::',
                inline=False,
                value=(
                    html_to_md(issue_result.happening.capitalize() + '.')
                    + reclassifications
                )
            )
        if issue_result.headlines:
            embed.add_field(
                name=':newspaper::',
                inline=False,
                value=(
                    ';\n'.join((
                        html_to_md(headline)
                        for headline in issue_result.headlines))
                    + '.'
                )
            )
        if issue_result.census:
            embed.add_field(
                name=':chart_with_upwards_trend::',
                inline=False,
                value=(
                    '```diff\n{}\n```'
                    .format('\n'.join(census_difference(issue_result.census)))
                )
            )
        await self.client.send_message(
            self.issue_channel,
            'Legislation Passed:',
            embed=embed
        )
        for banner in issue_result.banners:
            embed = discord.Embed(
                title=banner.name,
                description=banner.validity,
                colour=discord.Colour(0x36393e),
            )
            embed.set_image(url=banner.url)
            await self.client.send_message(
                self.issue_channel,
                'New banner unlocked:',
                embed=embed
            )

    async def open_issue(self, issue):
        embed = discord.Embed(
            title=issue.title,
            description=html_to_md(issue.text),
            colour=discord.Colour(0xfdc82f),
            timestamp=datetime.utcnow()
        )

        if issue.banners:
            embed.set_image(url=issue.banners[0].url)

        embed.set_thumbnail(url=self.nation_flag)

        for i, option in enumerate(issue.options):
            embed.add_field(
                name=number_to_emoji[i] + ':',
                value=html_to_md(option.text)
            )

        message = await self.client.send_message(
            self.issue_channel,
            f'Issue #{issue.id}:',
            embed=embed
        )
        for i in range(len(issue.options)):
            await self.client.add_reaction(message, number_to_emoji[i])
        await self.client.send_message(
            self.inform_channel,
            f'New issue: **{issue.title}**\n'
            f'Head over to {self.issue_channel.mention} for more.'
        )

    async def get_last_issue_message(self):
        async for message in self.client.logs_from(self.issue_channel,
                                                   limit=50):
            if (message.author == self.client.user and
                    message.content.startswith('Issue #')):
                return message


    def wait_until_first_issue(self):
        now = datetime.utcnow()
        today_seconds = (
            now.timestamp()
            - (now
               .replace(hour=0, minute=0, second=0, microsecond=0)
               .timestamp())
        )
        to_sleep = (
            self.issue_period - today_seconds % self.issue_period
            + self.first_issue_offset
        )
        logger.info(f'sleeping {to_sleep} seconds before starting the'
                    f' issue cycle loop for {self.nation.id}')
        return asyncio.sleep(to_sleep)


    async def issue_cycle(self):
        nation_name, self.nation_flag, issues = await (
            self.nation.name() + self.nation.flag() + self.nation.issues())
        if not self.client.user.name == nation_name:  # ratelimit :(
            await self.client.edit_profile(username=nation_name)

        issues = list(reversed(issues))
        
        last_issue_message = await self.get_last_issue_message()
        # TODO pythonicize
        if (last_issue_message and
                last_issue_message.content == f'Issue #{issues[0].id}:'):
            results = list(vote_results(last_issue_message, issues[0]))
            _, max_votes = max(results, key=itemgetter(1))
            option = random.choice(
                [option for option, votes in results if votes == max_votes])

            await self.close_issue(issues[0], option)
            logger.info(f'close issue {issues[0].id} for {self.nation.id}')
            await self.open_issue(issues[1])
            logger.info(f'open next issue {issues[1].id} for {self.nation.id}')
        else:
            await self.open_issue(issues[0])
            logger.info(f'open first issue {issues[0].id} for {self.nation.id}')


    async def issue_cycle_loop(self):
        await self.client.wait_until_ready()

        # TODO make less ugly and terrible
        self.issue_channel = self.client.get_channel(self.issue_channel)
        self.inform_channel = self.client.get_channel(self.inform_channel)

        await self.client.change_presence(
            game=discord.Game(name='NationStates'))

        await self.wait_until_first_issue()

        while not self.client.is_closed:
            logger.info(f'start cycle for {self.nation.id}')
            started_at = time.time()

            try:
                await self.issue_cycle()
            except:
                logger.error(f'for {self.nation.id}:\n'
                             + traceback.format_exc())

            logger.info(f'end cycle for {self.nation.id}')
            finished_at = time.time()
            delta = finished_at - started_at
            await asyncio.sleep(self.issue_period - delta)


if __name__ == "__main__":
    with open('config.json') as f:
        config = json.load(f)
    with suppress(KeyError):
        logging.config.dictConfig(config['LOGGING'])

    aionationstates.USER_AGENT = config['USER-AGENT']

    instances = []
    for instance in config['INSTANCES']:
        instances.append(DPNInstance(
            api_key=instance['API_KEY'],
            issue_channel=instance['ISSUES_CHANNEL'],
            inform_channel=instance['INFORM_CHANNEL'],
            nation=aionationstates.NationControl(
                instance['NATION'],
                autologin=instance.get('AUTOLOGIN') or '',
                password=instance.get('PASSWORD') or ''
            ),
            issue_period=instance.get('ISSUE_PERIOD') or 21600,  # 6 hours
            first_issue_offset=instance.get('ISSUE_OFFSET') or 0
        ))

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(
            # Await all Tasks, so that exceptions in them can propagate.
            # Otherwise the program remains frozen until you manually
            # kill it, when it prints the "Task exception was never
            # retrieved" error message.
            #
            # This feels like a hack, but I'm not sure there's a better way.
            asyncio.gather(*asyncio.Task.all_tasks()))
    except:
        for instance in instances:
            # Disable the "Task was destroyed but it is pending!"
            # error message. We already know the error occured, no
            # need to spam the log.
            instance.issue_cycle_loop_task._log_destroy_pending = False
            loop.run_until_complete(instance.client.logout())
        raise
    finally:
        loop.close()


