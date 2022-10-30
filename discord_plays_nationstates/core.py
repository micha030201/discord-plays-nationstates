# Standard
import asyncio
import collections
import datetime
import logging
import random
import itertools

# Typing
from typing import Dict, Iterator, List, Optional

# External
import aionationstates
import discord
import discord.ext.commands as discord_cmds

# Global
OptionList = List[aionationstates.IssueOption]
logger = logging.getLogger('discord-plays-nationstates')


# Helper functions:

def html_to_md(html: str):
    return html.replace('*', '\*').replace('<i> ', ' *').replace(' </i>', '* ').replace('&quot;', '"')


EMOJIS = (
    '0⃣', '1⃣', '2⃣', '3⃣', '4⃣', '5⃣', '6⃣', '7⃣', '8⃣', '9⃣', '🔟',
    '♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓', '⛎',
    )


def text_fragments(text: str, sep='. ', limit=1024):
    fragment: str
    fragment_list: List[str] = []
    for fragment in text.split(sep):
        if fragment_list and len(sep.join(fragment_list + [fragment])) > limit:
            yield sep.join(fragment_list)
            fragment_list = [fragment]
        else:
            fragment_list.append(fragment)
    yield sep.join(fragment_list)


def census_difference(census_change_list: List[aionationstates.CensusScaleChange], sep='\r\n', limit=1024):
    index: int = int(0)
    change_list: List[str] = []
    final_str = sep.join(change_list)
    results_sorted = sorted(census_change_list, key=lambda scale: abs(scale.pchange), reverse=True)
    for census_change in results_sorted:
        if census_change.pchange > 0.005:
            change_str = f'+{census_change.info.title:<35} ↑{census_change.pchange:.2f}%'
            change_list.insert(index, change_str)
            new_str = sep.join(change_list)
            index += 1
        elif census_change.pchange < -0.005:
            change_str = f'-{census_change.info.title:<35} ↓{-census_change.pchange:.2f}%'
            change_list.insert(index, change_str)
            new_str = sep.join(change_list)
        else:
            continue
        if len(new_str) > limit:
            break
        final_str = new_str
    return final_str


# Bot class:

class IssueAnswerer(object):
    issue_open_colour = discord.Colour(0xfdc82f)
    issue_result_colour = discord.Colour(0xde3831)
    banner_colour = discord.Colour(0x36393e)

    def __init__(
            self,
            between_issues: datetime.timedelta,
            first_issue_offset: datetime.time,
            nation: aionationstates.NationControl,
            channel: discord.TextChannel,
            owner_id: int,
            ):
        self.between_issues = between_issues
        self.first_issue_offset = first_issue_offset
        self.owner_id = owner_id
        self.channel = channel
        self.nation = nation

        my_task = self.issue_cycle_loop()
        self.task = asyncio.get_event_loop().create_task(my_task)

    def description(self):
        return self.nation.description()

    def get_countdown_str(self):
        wait_until_next_issue = self.get_wait_until_next_issue()
        hours = int(wait_until_next_issue // 3600)
        minutes = int(wait_until_next_issue % 3600 // 60)
        seconds = int(wait_until_next_issue % 60)
        countdown_str = (
            f'Issue cycle will sleep {hours} hours, {minutes} '
            f'minutes, and {seconds} seconds until next issue.')
        return countdown_str

    async def close_issue(self, issue: aionationstates.Issue, option: aionationstates.IssueOption):
        issue_result: aionationstates.IssueResult = await option.accept()
        md_text = html_to_md(issue.text)
        embed = discord.Embed(title=issue.title, description=md_text, colour=self.issue_result_colour)

        # Selected option:
        name = ':white_check_mark::'
        md_text = html_to_md(option.text)
        fragment_gen = text_fragments(md_text)
        for index, partial_text in enumerate(fragment_gen, start=1):
            embed.add_field(name=name, value=partial_text, inline=False)
            name = ':white_check_mark::-%d' % index

        # Effect line + reclassifications:
        effect_line: str = issue_result.effect_line or 'issue was dismissed'
        effect = effect_line.capitalize() + '.'
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
            census_lines = census_difference(issue_result.census, sep='\n', limit=1024-12)
            embed.add_field(name=':chart_with_upwards_trend::', inline=False, value=f'```diff\n{census_lines}\n```')

        await self.channel.send('Legislation Passed:', embed=embed)

        # Banners:
        async def post_banner(banner):
            embed = discord.Embed(title=banner.name, description=banner.validity, colour=self.banner_colour)
            embed.set_image(url=banner.url)
            await self.channel.send('New banner unlocked:', embed=embed)

        # Policies:
        def policy_embed(policy):
            embed = discord.Embed(title=policy.name, description=policy.description, colour=self.banner_colour)
            embed.set_image(url=policy.banner)
            return embed

        async def post_new_policy(policy):
            await self.channel.send('New policy introduced:', embed=policy_embed(policy))

        async def post_removed_policy(policy):
            await self.channel.send('Removed policy:', embed=policy_embed(policy))

        await asyncio.gather(
            *map(post_banner, issue_result.banners),
            *map(post_new_policy, issue_result.new_policies),
            *map(post_removed_policy, issue_result.removed_policies),
            )

    async def open_issue(self, issue: aionationstates.Issue, nation_flag: str):
        md_text = html_to_md(issue.text)
        utcnow = datetime.datetime.utcnow()
        embed = discord.Embed(title=issue.title, description=md_text, colour=self.issue_open_colour, timestamp=utcnow)

        if issue.banners:
            banner_url, *extra = issue.banners
            embed.set_image(url=banner_url)

        embed.set_thumbnail(url=nation_flag)

        reactions = []
        for option, emoji in self.yield_options_with_emoji(issue):
            name = emoji + f': {option._id + 1:d}'
            md_text = html_to_md(option.text)
            fragment_gen = text_fragments(md_text)
            for index, partial_text in enumerate(fragment_gen, start=1):
                embed.add_field(name=name, value=partial_text, inline=False)
                name = emoji + ':-%d' % index
            reactions.append(emoji)

        message: discord.Message = await self.channel.send(f'Issue #{issue.id}:', embed=embed)
        for emoji in reactions:
            await message.add_reaction(emoji)
        return message

    async def vote_results(self, message: discord.Message, issue: aionationstates.Issue):
        option_per_react_id: Dict[int, aionationstates.IssueOption] = {}
        reactions_grouped_by_count: Dict[int, List[discord.Reaction]] = collections.defaultdict(list)
        reaction: discord.Reaction
        debug_str = 'Found reaction (%s) with (%d) votes.'
        options: OptionList = [Dismiss(issue)] + issue.options
        for reaction in message.reactions:
            if not reaction.me:
                continue

            assert options, 'Too many reactions for the set of options.'
            logger.debug(debug_str, reaction.emoji, reaction.count)
            reactions_grouped_by_count[reaction.count].append(reaction)
            option_per_react_id[id(reaction)] = options.pop(0)

        assert not options, 'One or more options lack a reaction.'
        max_count: int = max(reactions_grouped_by_count)
        results: List[discord.Reaction] = reactions_grouped_by_count[max_count]

        owner_picks: OptionList = []
        tied_options: OptionList = []
        for reaction in results:
            react_option = option_per_react_id[id(reaction)]
            voters = await reaction.users().flatten()
            voter_set = set(voter.id for voter in voters)
            if self.owner_id in voter_set:
                owner_picks.append(react_option)
            tied_options.append(react_option)

        if owner_picks:
            return random.choice(owner_picks)
        return random.choice(tied_options)

    def get_wait_until_next_issue(self):
        utc_now = datetime.datetime.utcnow()
        first_issue_today = datetime.datetime.combine(utc_now.date(), self.first_issue_offset)
        since_first_issue_today = utc_now - first_issue_today
        since_last_issue = since_first_issue_today % self.between_issues
        until_next_issue = self.between_issues - since_last_issue
        return until_next_issue.total_seconds()

    async def issue_cycle(self):
        lookup_issue_by_msg = await self.get_issue_dict()
        if not lookup_issue_by_msg:
            await self.channel.send('Nation has no issues.')
            return

        next_issue_message: Optional[discord.Message] = None
        logger.info('Begin channel history scan, remaining issues %d', len(lookup_issue_by_msg))

        message: discord.Message
        channel_guild_me: discord.Member = self.channel.guild.me
        earliest = datetime.datetime.now() - datetime.timedelta(days=2)
        async for message in self.channel.history(after=earliest):
            if message.author != channel_guild_me:
                continue

            if message.content not in lookup_issue_by_msg:
                continue

            issue: aionationstates.Issue = lookup_issue_by_msg.pop(message.content)
            options_with_emoji = self.yield_options_with_emoji(issue)
            required_reactions = set(emoji for option, emoji in options_with_emoji)
            stated_reactions = set(reaction.emoji for reaction in message.reactions if reaction.me)

            if required_reactions != stated_reactions:
                logger.info(message.content + ' options have changed, post will be deleted and replaced.')
                await message.delete()
                await self.channel.send(message.content + ' is being replaced, all previous votes are discarded.')
                continue

            if len(lookup_issue_by_msg) >= 4:
                logger.info(f'Now collecting votes for the close of issue {message.content} {issue.title}.')
                winning_option = await self.vote_results(message, issue)
                await self.close_issue(issue, winning_option)
                lookup_issue_by_msg = await self.get_issue_dict()
                continue

            if next_issue_message is None:
                next_issue_message = message
            logger.info('Issue %s ready, remaining issues %d', f'{message.content} {issue.title}', len(lookup_issue_by_msg))

        if lookup_issue_by_msg:
            nation_flag = await self.nation.flag()
        for issue in lookup_issue_by_msg.values():
            issue_message = await self.open_issue(issue, nation_flag)
            if next_issue_message is None:
                next_issue_message = issue_message

        countdown_str = self.get_countdown_str()

        if next_issue_message is None:
            await self.channel.send(f'Next Issue message was lost. Pls fix <@{self.owner_id}>')
            return

        await self.channel.send(countdown_str, reference=next_issue_message, mention_author=False)

        reaction: discord.Reaction
        for reaction in next_issue_message.reactions:
            if not reaction.me:
                continue
            if reaction.count > 1:
                return
        msg_str = f'There are no votes yet <@{self.owner_id}>!'
        await self.channel.send(msg_str)

    async def get_issue_dict(self):
        lookup_issue_by_msg: Dict[str, aionationstates.Issue] = {}
        for issue in await self.nation.issues():
            id_str = f'Issue #{issue.id}:'
            if id_str in lookup_issue_by_msg:
                raise SystemExit(f'Issue id #{issue.id} was not unique.')
            lookup_issue_by_msg[id_str] = issue
        return lookup_issue_by_msg

    @staticmethod
    def yield_options_with_emoji(issue: aionationstates.Issue):
        options: OptionList = [Dismiss(issue)] + issue.options
        for option in options:
            emoji = EMOJIS[option._id + 1]
            yield option, emoji

    async def issue_cycle_loop(self):
        while True:
            wait_until_next_issue = self.get_wait_until_next_issue()
            await asyncio.sleep(wait_until_next_issue)
            try:
                await self.issue_cycle()
            except Exception:
                logger.exception('Error while cycling issues:')
                await self.channel.send(f'Issue cycle error. Pls fix <@{self.owner_id}>')


class Dismiss(aionationstates.IssueOption):
    ''' Option to dismiss issue. '''

    def __init__(self, issue):
        self._issue = issue
        self._id = -1
        self.text = aionationstates.utils.unscramble_encoding('Dismiss issue.')


# Commands:

@discord_cmds.command()
async def issues(ctx: discord_cmds.Context, nation: aionationstates.Nation = None):
    """What's this?"""
    jobs: List[IssueAnswerer] = []
    for job in _jobs:
        if job.channel not in ctx.guild.channels:
            continue
        if nation is not None and job.nation.id == nation.id:
            description = await job.description()
            await ctx.send(description)
            return
        jobs.append(job)

    messages = await asyncio.gather(*[job.description() for job in jobs])
    await asyncio.gather(*map(ctx.send, messages))


@discord_cmds.command()
async def countdown(ctx: discord_cmds.Context, nation: aionationstates.Nation = None):
    """Report time to next auto cycle."""
    messages: List[str] = []
    for job in _jobs:
        if job.channel not in ctx.guild.channels:
            continue
        countdown_str = job.get_countdown_str()
        if nation is not None and job.nation.id == nation.id:
            await ctx.send(countdown_str)
            return
        messages.append(countdown_str)

    await asyncio.gather(*map(ctx.send, messages))


@discord_cmds.command(hidden=True)
@discord_cmds.is_owner()
async def scroll(ctx: discord_cmds.Context, nation: aionationstates.Nation = None):
    """Switch the issues manually."""
    nations_to_jobs = {job.nation: job for job in _jobs}

    if nation is not None:
        job = nations_to_jobs[nation]
    elif len(_jobs) == 1:
        job = _jobs[0]
    else:
        logger.error('Scroll failed, nation not specified and found %d jobs.', len(_jobs))
        return
    await job.issue_cycle()


@discord_cmds.command(hidden=True)
@discord_cmds.is_owner()
async def shutdown(ctx: discord_cmds.Context, nation: aionationstates.Nation = None):
    await ctx.send('Shutting down as requested.')
    for job in _jobs:
        job.task.cancel()
    logger.info('All tasks closed.')
    bot: discord_cmds.Bot = ctx.bot
    await bot.close()


# Loading & unloading:

_jobs: List[IssueAnswerer] = []


# called by discord.py on bot.load_extension()
def setup(bot: discord_cmds.Bot):
    bot.add_command(issues)
    bot.add_command(countdown)
    bot.add_command(scroll)
    bot.add_command(shutdown)


# Public interface:

def instantiate(
        nation: aionationstates.NationControl,
        channel: discord.TextChannel,
        owner_id: int, *,
        issues_per_day=4,
        first_issue_offset=0,
        ):
    """Create a new issue-answering job.

        Parameters
        ----------
        nation : :class:`aionationstates.NationControl`
            The nation you want to post issues of.
        channel : :class:`discord.Channel`
            The channel you want the bot to post issues in.
        owner_id : int
            discord app owner identification integer
        issues_per_day : int
            How many issues to post per day.
        first_issue_offset : int
            How soon after UTC midnight to post the first issue of the day.
        """
    assert first_issue_offset >= 0, 'first_issue_offset must be greater than or equal to zero'
    assert issues_per_day in (1, 2, 3, 4), 'issues_per_day must be between one and four inclusive'
    assert first_issue_offset * issues_per_day <= 24, 'first_issue_offset must not exceed the time between issues'

    between_issues = datetime.timedelta(hours=24 / issues_per_day)
    initial_offset = datetime.timedelta(hours=first_issue_offset)
    min_start: datetime.datetime = datetime.datetime.min + initial_offset
    first_issue_offset = min_start.time()

    issue_answerer = IssueAnswerer(
        between_issues=between_issues,
        first_issue_offset=first_issue_offset,
        owner_id=owner_id,
        nation=nation,
        channel=channel,
        )

    _jobs.append(issue_answerer)
