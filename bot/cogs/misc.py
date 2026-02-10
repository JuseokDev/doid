from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

if TYPE_CHECKING:
    from bot import Bot

logger = logging.getLogger("bot.misc")


class Misc(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    @property
    def is_verified(self):
        return self.bot.user.public_flags.verified_bot

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        logger.info(f"[Guild] Bot has joined a new guild: {guild.name}")
        guild_count = len(self.bot.guilds)
        if not self.is_verified and guild_count >= 75:
            logger.warning(f"[Verification] Bot verification required: Bot reached {guild_count}/100 guilds")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        logger.info(f"[Guild] Bot has been removed from guild: {guild.name}")


async def setup(bot: Bot):
    await bot.add_cog(Misc(bot))
