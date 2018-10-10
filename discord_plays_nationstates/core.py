import random
import asyncio
import logging
from datetime import datetime, timedelta
from operator import itemgetter
from itertools import islice

import aionationstates
import discord
from discord.ext import commands


logger = logging.getLogger('discord-plays-nationstates')


# Helper functions:

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


# Bot class:

class IssueAnswerer:
    def __init__(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

        self.task = asyncio.get_event_loop().create_task(
            self.issue_cycle_loop())

    async def info(self):
        return await self.nation.description()

    async def close_issue(self, issue, option):
        issue_result = await option.accept()
        embed = discord.Embed(
            title=issue.title,
            description=html_to_md(issue.text),
            colour=discord.Colour(0xde3831),
        )

        # Selected option:
        embed.add_field(
            name=':white_check_mark::',
            inline=False,
            value=html_to_md(option.text)
        )

        # Effect line + reclassifications:
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

        # Headlines
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

        # Census:
        if issue_result.census:
            embed.add_field(
                name=':chart_with_upwards_trend::',
                inline=False,
                value=(
                    '```diff\n'
                    + '\n'.join(census_difference(issue_result.census))
                    + '\n```'
                )
            )

        await self.channel.send('Legislation Passed:', embed=embed)

        # Banners:
        async def post_banner(banner):
            embed = discord.Embed(
                title=banner.name,
                description=banner.validity,
                colour=discord.Colour(0x36393e),
            )
            embed.set_image(url=banner.url)
            await self.channel.send('New banner unlocked:', embed=embed)

        # Policies:
        def policy_embed(policy):
            embed = discord.Embed(
                title=policy.name,
                description=policy.description,
                colour=discord.Colour(0x36393e),
            )
            embed.set_image(url=policy.banner)
            return embed

        async def post_new_policy(policy):
            await self.channel.send('New policy introduced:',
                                    embed=policy_embed(policy))

        async def post_removed_policy(policy):
            await self.channel.send('Removed policy:',
                                    embed=policy_embed(policy))

        await asyncio.gather(
            *map(post_banner, issue_result.banners),
            *map(post_new_policy, issue_result.new_policies),
            *map(post_removed_policy, issue_result.removed_policies)
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

        message = await self.channel.send(f'Issue #{issue.id}:', embed=embed)
        for i in range(len(issue.options)):
            await message.add_reaction(number_to_emoji[i])

    async def vote_results(self, issue):
        def result(message, issue):
            reactions = {
                reaction.emoji: reaction.count
                for reaction in message.reactions}
            for option in issue.options:
                option_emoji = number_to_emoji[option]
                yield option, reactions[option_emoji]

        async for message in self.channel.history(limit=50):
            if (message.author == self.channel.guild.me and
                    message.content.startswith('Issue #')):
                if message.content == f'Issue #{issue.id}:':
                    return list(result(message, issue))
                else:
                    logger.error(
                        "Previous issue in channel doesn't match oldest "
                        "issue of nation, discarding."
                    )
                    break

        raise LookupError

    def wait_until_next_issue(self):
        this_midnight = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0)
        since_first_issue_today = (datetime.utcnow()
                                   - this_midnight
                                   + self.first_issue_offset)
        since_last_issue = since_first_issue_today % self.between_issues
        until_next_issue = self.between_issues - since_last_issue
        return asyncio.sleep(until_next_issue.total_seconds())

    async def issue_cycle(self):
        self.nation_flag, issues = await (
            self.nation.flag() + self.nation.issues())

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
        while True:
            await self.wait_until_next_issue()
            try:
                await self.issue_cycle()
            except Exception:
                logger.exception('Error while cycling issues:')


# Commands:

@commands.command()
async def issues(ctx, nation: aionationstates.Nation = None):
    """What's this?"""
    nations_to_jobs = {job.nation: job
                       for job in _jobs
                       if job.channel in ctx.guild.channels}

    try:
        jobs = (nations_to_jobs[nation],)
    except KeyError:
        jobs = nations_to_jobs.values()

    messages = await asyncio.gather(*[job.info() for job in jobs])
    await asyncio.gather(*map(ctx.send, messages))


@commands.command(hidden=True)
@commands.is_owner()
async def scroll(ctx, nation: aionationstates.Nation = None):
    """Switch the issues manually."""
    nations_to_jobs = {job.nation: job for job in _jobs}

    if nation is None and len(nations_to_jobs) == 1:
        await nations_to_jobs.popitem()[1].issue_cycle()
    else:
        await nations_to_jobs[nation].issue_cycle()


# Loading & unloading:

_jobs = []


# called by discord.py on bot.load_extension()
def setup(bot):
    bot.add_command(issues)
    bot.add_command(scroll)


# called by discord.py on bot.unload_extension()
def teardown():
    for job in _jobs:
        job.task.cancel()


# Public interface:

def instantiate(nation, channel, *, issues_per_day=4,
                first_issue_offset=timedelta(0)):
    """Create a new issue-answering job.

    Parameters
    ----------
    nation : :class:`aionationstates.NationControl`
        The nation you want to post issues of.
    channel : :class:`discord.Channel`
        The channel you want the bot to post issues in.
    issues_per_day : int
        How many issues to post per day.
    first_issue_offset : :class:`datetime.timedelta`
        How soon after UTC midnight to post the first issue of the day.
    """
    if type(issues_per_day) is not int or not 1 <= issues_per_day <= 4:
        raise ValueError('issues_per_day must be an'
                         ' integer between 1 and 4')
    between_issues = timedelta(days=1) / issues_per_day

    if first_issue_offset >= between_issues:
        raise ValueError('first_issue_offset must not exceed the'
                         ' time between issues')

    _jobs.append(IssueAnswerer(
        between_issues=between_issues,
        first_issue_offset=first_issue_offset,
        nation=nation,
        channel=channel,
    ))
