import sys
import re
from os import path
from setuptools import setup


here = path.abspath(path.dirname(__file__))


with open(path.join(here, 'discord_plays_nationstates/__init__.py')) as f:
    version_match = re.search("__version__ = '(.+?)'", f.read())
    if version_match:
        version = version_match.group(1)
    else:
        raise RuntimeError("Unable to find version string.")


with open(path.join(here, 'README.rst')) as f:
    long_description = f.read()


setup(
    name='discord-plays-nationstates',

    version=version,

    description='A discord bot that answers issues as a NationStates nation',
    long_description=long_description,

    url='https://github.com/micha030201/discord-plays-nationstates',

    author='Михаил Лебедев',
    author_email='micha030201@gmail.com',

    license='AGPLv3+',

    classifiers=[
        'Development Status :: 3 - Alpha',

        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'Topic :: Internet',
        'Topic :: Games/Entertainment :: Simulation',
        'Natural Language :: English',

        'License :: OSI Approved :: GNU Affero General Public License v3 or later (AGPLv3+)',

        'Programming Language :: Python :: 3.6',
        'Framework :: AsyncIO',
    ],

    keywords='nationstates chatbot',

    packages=['discord_plays_nationstates'],

    install_requires=['aionationstates', 'discord.py'],
    python_requires=">=3.6.1",

    entry_points={
        'console_scripts': ['discord-plays-nationstates=discord_plays_nationstates.run:main'],
    }
)
