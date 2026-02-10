from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import LayoutView

if TYPE_CHECKING:
    from bot import Bot

logger = logging.getLogger("bot.settings")


class SettingsView(LayoutView):
    pass


class Settings(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot


async def setup(bot: Bot):
    await bot.add_cog(Settings(bot))
