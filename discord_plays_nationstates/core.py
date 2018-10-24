import random
import asyncio
import logging

import datetime
import operator
import itertools

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
    -1: '0⃣', 0: '1⃣', 1: '2⃣', 2: '3⃣',
    3: '4⃣', 4: '5⃣', 5: '6⃣', 6: '7⃣',
    7: '8⃣', 8: '9⃣', 9: '🔟'}
emoji_to_number = dict(reversed(i) for i in number_to_emoji.items())


def census_difference(census_change):
    results = (
        (scale.info.title, scale.pchange)
        for scale in census_change)
    mapping = (
        sorted(
            itertools.islice(
                sorted(
                    results,
                    key=lambda x: abs(x[1]),
                    reverse=True),
                11),
            key=operator.itemgetter(1),
            reverse=True))
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
        embed = discord.Embed(title=issue.title, description=html_to_md(issue.text), colour=discord.Colour(0xde3831))

        # Selected option:
        embed.add_field(name=':white_check_mark::', inline=False, value=html_to_md(option.text))

        # Effect line + reclassifications:
        effect = issue_result.effect_line
        # str.capitalize() lowercases the rest of the string.
        effect = f'{effect[0].upper()}{effect[1:]}.'
        if issue_result.reclassifications:
            reclassifications = ";\n".join(issue_result.reclassifications)
            effect += f'\n\n{reclassifications}.'
        embed.add_field(name=':pencil::', inline=False, value=html_to_md(effect))

        # Headlines
        if issue_result.headlines:
            text = ';\n'.join(html_to_md(headline) for headline in issue_result.headlines) + '.'
            embed.add_field(name=':newspaper::', inline=False,value=text)

        # Census:
        if issue_result.census:
            text = '```diff\n' + '\n'.join(census_difference(issue_result.census)) + '\n```'
            embed.add_field(name=':chart_with_upwards_trend::', inline=False, value=text)

        await self.channel.send('Legislation Passed:', embed=embed)

        # Banners:
        async def post_banner(banner):
            embed = discord.Embed(
                title=banner.name,
                description=banner.validity,
                colour=discord.Colour(0x36393e))
            embed.set_image(url=banner.url)
            await self.channel.send('New banner unlocked:', embed=embed)

        # Policies:
        def policy_embed(policy):
            embed = discord.Embed(
                title=policy.name,
                description=policy.description,
                colour=discord.Colour(0x36393e))
            embed.set_image(url=policy.banner)
            return embed

        async def post_new_policy(policy):
            await self.channel.send('New policy introduced:', embed=policy_embed(policy))

        async def post_removed_policy(policy):
            await self.channel.send('Removed policy:', embed=policy_embed(policy))

        await asyncio.gather(
            *map(post_banner, issue_result.banners),
            *map(post_new_policy, issue_result.new_policies),
            *map(post_removed_policy, issue_result.removed_policies))

    async def open_issue(self, issue):
        embed = discord.Embed(
            title=issue.title,
            description=html_to_md(issue.text),
            colour=discord.Colour(0xfdc82f),
            timestamp=datetime.datetime.utcnow())

        if issue.banners:
            embed.set_image(url=issue.banners[0])

        embed.set_thumbnail(url=self.nation_flag)

        for i, option in enumerate([Dismiss(issue)] + issue.options, -1):
            embed.add_field(name=number_to_emoji[i] + ':', value=html_to_md(option.text))

        message = await self.channel.send(f'Issue #{issue.id}:', embed=embed)
        for i in range(-1, len(issue.options)):
            await message.add_reaction(number_to_emoji[i])

    async def vote_results(self, issue):
        def result(message, issue):
            reaction_counts = {
                reaction.emoji: reaction.count
                for reaction in message.reactions}
            for index, option in enumerate([Dismiss(issue)] + issue.options, -1):
                option_emoji = number_to_emoji[index]
                yield option, reaction_counts[option_emoji]

        async for message in self.channel.history(limit=50):
            if message.author != self.channel.guild.me:
                continue
            if not message.content.startswith('Issue #'):
                continue
            if message.content == f'Issue #{issue.id}:':
                results = list(result(message, issue))
                return results
            logger.error(
                "Previous issue in channel doesn't match oldest "
                "issue of nation, discarding.")
            break

        raise LookupError

    def wait_until_next_issue(self):
        this_midnight = datetime.datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0)
        since_first_issue_today = (
            datetime.datetime.utcnow() - this_midnight + self.first_issue_offset)
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
            logger.exception('vote results error')
            await self.open_issue(issues[0])
        else:
            _, max_votes = max(results, key=operator.itemgetter(1))
            winning_options = [option for option, votes in results if votes == max_votes]
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


class Dismiss:
    """ To dismiss an issue.
        Attributes
        ----------
        text : str
            The option text.  May contain HTML elements and character references.
        """

    def __init__(self, issue):
        self._issue = issue
        self._id = -1
        self.text = aionationstates.utils.unscramble_encoding('Dismiss issue.')

    def accept(self):
        """ Accept the option.
            Returns
            -------
            an awaitable of :class:`IssueResult`
            """
        return self._issue._nation._accept_issue(self._issue.id, self._id)

    def __repr__(self):
        return f'<Option {self._id} of issue #{self._issue.id}>'


# Commands:

@commands.command()
async def issues(ctx, nation: aionationstates.Nation = None):
    """What's this?"""
    nations_to_jobs = {job.nation: job for job in _jobs if job.channel in ctx.guild.channels}

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

def instantiate(nation, channel, *, issues_per_day=4, first_issue_offset=0):
    """Create a new issue-answering job.

        Parameters
        ----------
        nation : :class:`aionationstates.NationControl`
            The nation you want to post issues of.
        channel : :class:`discord.Channel`
            The channel you want the bot to post issues in.
        issues_per_day : int
            How many issues to post per day.
        first_issue_offset : int
            How soon after UTC midnight to post the first issue of the day.
        """
    assert isinstance(issues_per_day, int) and 1 <= issues_per_day <= 4, (
        'issues_per_day must be an integer between 1 and 4')
    between_issues = 4 / issues_per_day

    assert first_issue_offset >= 0, (
        'first_issue_offset must be an integer greater than or equal to zero')
    assert first_issue_offset < 24 / issues_per_day, (
        'first_issue_offset must not exceed the time between issues')

    _jobs.append(IssueAnswerer(
        first_issue_offset=datetime.timedelta(hours=first_issue_offset),
        between_issues=between_issues, nation=nation, channel=channel))
