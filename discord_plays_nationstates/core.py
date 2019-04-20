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


EMOJIS = ('0⃣', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟')


def census_difference(census_change):
    results = (
        (scale.info.title, scale.pchange)
        for scale in census_change)
    results_sorted = sorted(results, key=lambda x: abs(x[1]), reverse=True)
    sliced = itertools.islice(results_sorted, 11)
    mapping = sorted(sliced, key=operator.itemgetter(1), reverse=True)
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

class IssueAnswerer(object):
    def __init__(self, first_issue_offset, between_issues, nation, channel, owner_id):
        self.first_issue_offset = first_issue_offset
        self.between_issues = between_issues
        self.owner_id = owner_id
        self.channel = channel
        self.nation = nation

        my_task = self._issue_cycle_loop()
        self.task = asyncio.get_event_loop().create_task(my_task)

    async def info(self):
        return await self.nation.description()

    async def countdown(self):
        issues = await self.nation.issues()
        if issues:
            *remaining_issues, current_issue = issues
            try:
                winning_option: aionationstates.IssueOption = await self._vote_results(current_issue)
                logger.debug('Countdown vote yielded winning option text:\n%s', winning_option.text)
            except LookupError:
                logger.debug('LookupError')
        wait_until_next_issue = self.wait_until_next_issue()
        return countdown_str(wait_until_next_issue)

    async def _close_issue(self, issue: aionationstates.Issue, option: aionationstates.IssueOption):
        issue_result: aionationstates.IssueResult = await option.accept()
        embed = discord.Embed(
            title=issue.title,
            description=html_to_md(issue.text),
            colour=discord.Colour(0xde3831))

        # Selected option:
        embed.add_field(name=':white_check_mark::', inline=False, value=html_to_md(option.text))

        # Effect line + reclassifications:
        effect_line = issue_result.effect_line or 'issue was dismissed'
        effect = f'{effect_line.capitalize()}.'
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

    async def _open_issue(self, issue: aionationstates.Issue):
        embed = discord.Embed(
            title=issue.title,
            description=html_to_md(issue.text),
            colour=discord.Colour(0xfdc82f),
            timestamp=datetime.datetime.utcnow())

        if issue.banners:
            banner_url, *extra = issue.banners
            embed.set_image(url=banner_url)

        nation_flag = await self.nation.flag()
        embed.set_thumbnail(url=nation_flag)

        reactions = []
        for option, emoji in zip([Dismiss(issue)] + issue.options, EMOJIS):
            embed.add_field(name=emoji + ':', value=html_to_md(option.text))
            reactions.append(emoji)

        message = await self.channel.send(f'Issue #{issue.id}:', embed=embed)
        for emoji in reactions:
            await message.add_reaction(emoji)

    async def _get_issue_post(self, issue: aionationstates.Issue):
        message: discord.Message
        async for message in self.channel.history(limit=50):
            if message.author != self.channel.guild.me:
                continue
            if not message.content.startswith('Issue #'):
                continue
            if message.content == f'Issue #{issue.id}:':
                return message
        return None

    async def _vote_results(self, issue: aionationstates.Issue):
        def result(message, issue):
            vote_max = 0
            reaction: discord.Reaction
            debug_str = 'Found reaction (%s) with (%d) votes.'
            for reaction in message.reactions:
                if reaction.emoji not in EMOJIS:
                    continue
                logger.debug(debug_str, reaction.emoji, reaction.count)
                if reaction.count < vote_max:
                    continue
                index = EMOJIS.index(reaction.emoji)
                option = (index, reaction)
                if reaction.count == vote_max:
                    results.append(option)
                    continue
                results = [option]
                vote_max = reaction.count
            return results

        message = await self._get_issue_post(issue)
        if message is None:
            raise LookupError(f'Issue #{issue.id} not found in recent channel history.')
        options = [Dismiss(issue)] + issue.options
        results = result(message, issue)
        top_pick, *tied = results
        if not tied:
            index, reaction = top_pick
            return options[index]
        logger.info('Vote is tied, looking for tie breaker: %s', self.owner_id)
        owner_picks = []
        reaction: discord.Reaction
        for index, reaction in results:
            voters = await reaction.users().flatten()
            voter_set = set(voter.id for voter in voters)
            if self.owner_id in voter_set:
                owner_picks.append(options[index])
        if owner_picks:
            if len(owner_picks) == 1:
                logger.info('App owner breaks tie.')
            return random.choice(owner_picks)
        tied_options = [options[index] for index, users in results]
        return random.choice(tied_options)

    def wait_until_next_issue(self):
        utc_now = datetime.datetime.utcnow()
        last_midnight = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
        since_first_issue_today = utc_now - (last_midnight + self.first_issue_offset)
        since_last_issue = since_first_issue_today % self.between_issues
        until_next_issue = self.between_issues - since_last_issue
        return until_next_issue.total_seconds()

    async def issue_cycle(self):
        issues = await self.nation.issues()
        if not issues:
            self.channel.send('Nation has no issues. Resuming cycle sleep.')
            return

        while len(issues) > 4:
            try:
                *issues, current_issue = issues
                winning_option = await self._vote_results(current_issue)
                await self._close_issue(current_issue, winning_option)
            except LookupError as exc:
                logger.error('Vote results error.')
                self.channel.send(*exc.args)
                await self._open_issue(current_issue)
                issues = [current_issue] + issues
                await asyncio.sleep(30)

        issues.reverse()
        issue: aionationstates.Issue
        for issue in issues:
            message = await self._get_issue_post(issue)
            if message is not None:
                continue
            await self._open_issue(issue)

    async def _issue_cycle_loop(self):
        while True:
            wait_until_next_issue = self.wait_until_next_issue()
            logger.info(countdown_str(wait_until_next_issue))
            await asyncio.sleep(wait_until_next_issue)
            try:
                await self.issue_cycle()
            except Exception:
                logger.exception('Error while cycling issues:')
                await self.channel.send('Issue cycle error. Resuming cycle sleep.')


def countdown_str(until_next_issue):
    hours = int(until_next_issue // 3600)
    minutes = int(until_next_issue % 3600 // 60)
    seconds = int(until_next_issue % 60)
    return f'Issue cycle will sleep {hours} hours, {minutes} minutes, and {seconds} seconds until next issue.'


class Dismiss(aionationstates.IssueOption):

    def __init__(self, issue):
        self._issue = issue
        self._id = -1
        self.text = aionationstates.utils.unscramble_encoding('Dismiss issue.')


# Commands:

@commands.command()
async def issues(ctx, nation: aionationstates.Nation = None):
    """What's this?"""
    nations_to_jobs = {job.nation: job for job in _jobs if job.channel in ctx.guild.channels}

    if nation in nations_to_jobs:
        jobs = (nations_to_jobs[nation],)
    else:
        jobs = nations_to_jobs.values()

    messages = await asyncio.gather(*[job.info() for job in jobs])
    await asyncio.gather(*map(ctx.send, messages))


@commands.command()
async def countdown(ctx, nation: aionationstates.Nation = None):
    """Report time to next auto cycle."""
    nations_to_jobs = {job.nation: job for job in _jobs if job.channel in ctx.guild.channels}

    if nation in nations_to_jobs:
        jobs = (nations_to_jobs[nation],)
    else:
        jobs = nations_to_jobs.values()

    messages = await asyncio.gather(*[job.countdown() for job in jobs])
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


@commands.command(hidden=True)
@commands.is_owner()
async def shutdown(ctx: commands.Context, nation: aionationstates.Nation = None):
    teardown()
    bot: commands.Bot = ctx.bot
    await bot.close()


# Loading & unloading:

_jobs = []


# called by discord.py on bot.load_extension()
def setup(bot):
    bot.add_command(issues)
    bot.add_command(countdown)
    bot.add_command(scroll)
    bot.add_command(shutdown)


# called by discord.py on bot.unload_extension()
def teardown():
    for job in _jobs:
        job.task.cancel()


# Public interface:

def instantiate(nation, channel, owner_id, *, first_issue_offset=0):
    """Create a new issue-answering job.

        Parameters
        ----------
        nation : :class:`aionationstates.NationControl`
            The nation you want to post issues of.
        channel : :class:`discord.Channel`
            The channel you want the bot to post issues in.
        owner_id : int
            discord app owner identification integer
        first_issue_offset : int
            How soon after UTC midnight to post the first issue of the day.
        """
    issues_per_day = 5
    between_issues = datetime.timedelta(hours=24 / issues_per_day)

    assert first_issue_offset >= 0, (
        'first_issue_offset must be an integer greater than or equal to zero')
    assert first_issue_offset * issues_per_day <= 24, (
        'first_issue_offset must not exceed the time between issues')
    fio_td = datetime.timedelta(hours=first_issue_offset)
    issue_answerer = IssueAnswerer(
        first_issue_offset=fio_td,
        between_issues=between_issues,
        owner_id=owner_id,
        nation=nation,
        channel=channel)

    _jobs.append(issue_answerer)
