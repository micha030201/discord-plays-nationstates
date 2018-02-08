discord-plays-nationstates - A Discord Bot
==========================================

discord-plays-nationstates is a `Discord <https://discordapp.com/>`_ bot developed to enable sharing the experience of governing a `NationStates <https://www.nationstates.net/>`_ nation with your fellow chatmates.

Installation
------------

.. code-block::

   pip install discord-plays-nationstates
   pip install -U git+https://github.com/Rapptz/discord.py@rewrite#egg=discord.py
   discord-plays-nationstates \
      --token YOUR_DISCORD_API_TOKEN \
      --useragent YOUR_NATIONSTATES_USERAGENT \
      --nation NAME_OF_YOUR_NATION \
      --password PASSWORD_TO_YOUR_NATION \
      --channel ID_OF_THE_DISCORD_CHANNEL_YOU_WANT_TO_USE

Usage
-----

.. code-block::

   usage: discord-plays-nationstates [-h] --token TOKEN --useragent USERAGENT
                                     --nation NATION --password PASSWORD
                                     --channel CHANNEL

   optional arguments:
     -h, --help            show this help message and exit

   required arguments:
     --token TOKEN         The token for your Discord bot
     --useragent USERAGENT
                           User-Agent header for the NationStates API
     --nation NATION       Name of the nation you want to answer issues of
     --password PASSWORD   Password to the nation
     --channel CHANNEL     ID of the Discord channel to use


Dependencies
------------

* `Python 3.6.1+ <https://python.org>`_ - Programming language
* `discord.py rewrite <https://github.com/Rapptz/discord.py>`_ - Wrapper for the Discord API
* `aionationstates <https://github.com/micha030201/aionationstates>`_ - Wrapper for the NationStates API

License
-------

.. code-block::

   discord-plays-nationstates - a bot to control a NationStates nation from a Discord chat.
   Copyright (C) 2018  Михаил Лебедев

   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU Affero General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU Affero General Public License for more details.

   You should have received a copy of the GNU Affero General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.
