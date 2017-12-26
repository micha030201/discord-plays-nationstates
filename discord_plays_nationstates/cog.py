import time
import random
import asyncio
import traceback
import logging.config
from datetime import datetime
from operator import itemgetter
from itertools import islice

import discord
from discord import commands


logger = logging.getLogger('discord-plays-nationstates')


def html_to_md(html):
    return (
        html
        .replace('*', '\*')
        .replace('<i> ', ' <i>')
        .replace(' </i>', '</i> ')
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


class DiscordPlaysNationstates:
    def __init__(self, bot, nation, *, issue_channel,
                 issue_period=21600, first_issue_offset=0):
        self.nation = nation
        self.issue_channel = issue_channel
        self.issue_period = issue_period
        self.first_issue_offset = first_issue_offset
        self.issue_cycle_loop_task = \
            asyncio.ensure_future(self.issue_cycle_loop())

    @commands.command(hidden=True)
    @commands.is_owner()
    async def scroll(self, ctx):
        await self.issue_cycle()

    async def close_issue(self, issue, option):
        issue_result = await option.accept()
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
        effect = issue_result.effect_line
        # str.capitalize() lowercases the rest of the string.
        effect = f'{effect[0].upper()}{effect[1:]}.'
        if issue_result.reclassifications:
            reclassifications = ";\n".join(issue_result.reclassifications)
            effect += f'\n\n{reclassifications}.'
        effect = html_to_md(effect)
        embed.add_field(
            name=':pencil::',
            inline=False,
            value=effect
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
            embed.set_image(url=issue.banners[0])

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

    async def vote_results(self, issue):
        def result(message, issue):
            for i, (reaction, option) in enumerate(zip(message.reactions,
                                                       issue.options)):
                assert reaction.emoji == number_to_emoji[i]
                yield option, reaction.count

        async for message in self.client.logs_from(self.issue_channel,
                                                   limit=50):
            if (message.author == self.client.user and
                    message.content.startswith('Issue #')):
                assert message.content == f'Issue #{issue.id}:'
                return list(result(message, issue))

        raise LookupError

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
        return asyncio.sleep(to_sleep)

    async def issue_cycle(self):
        nation_name, self.nation_flag, issues = await (
            self.nation.name() + self.nation.flag() + self.nation.issues())

        issues.reverse()

        try:
            results = await self.vote_results(issues[0])
        except LookupError:
            await self.open_issue(issues[0])
        else:
            _, max_votes = max(results, key=itemgetter(1))
            winning_options = [option for option, votes in results
                               if votes == max_votes]
            winning_option = random.choice(winning_options)

            await self.close_issue(issues[0], winning_option)
            await self.open_issue(issues[1])

    async def issue_cycle_loop(self):
        await self.bot.wait_until_ready()

        await self.wait_until_first_issue()

        while True:
            started_at = time.time()

            try:
                await self.issue_cycle()
            except Exception:
                logger.exception('Error while changing issues:')

            finished_at = time.time()
            delta = finished_at - started_at
            await asyncio.sleep(self.issue_period - delta)
