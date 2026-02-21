from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.app_commands import locale_str as _T
from discord.ext import commands
from discord.ui import Container, LayoutView

from models import GuildSettings

if TYPE_CHECKING:
    from bot import Bot

logger = logging.getLogger("bot.settings")


class BaseContainer(Container):
    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__()
        self.bot: Bot = bot
        self.database = self.bot.database
        self.guild_id = interaction.guild_id

    async def load(self):
        pass


class GeneralSettings(BaseContainer):
    name = "general"

    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__(bot, interaction)

    async def load(self):
        pass


class VolumeSettings(BaseContainer):
    name = "volume"

    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__(bot, interaction)

    async def load(self):
        pass


class SettingsView(LayoutView):
    def __init__(self, bot: Bot, interaction: discord.Interaction, *, timeout=60):
        super().__init__(timeout=timeout)
        self.user_id = interaction.user.id
        self.pages: list[BaseContainer] = []
        self.index = 0

    async def load(self):
        for page in self.pages:
            await page.load()

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return False
        return True

    async def on_timeout(self):
        pass


class Settings(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.database = self.bot.database

    @commands.Cog.listener()
    async def on_ready(self):
        database = self.bot.database
        guilds = await database.database["guild_settings"].distinct("guild_id")
        for guild in self.bot.guilds:
            if guild.id in guilds:
                continue

            await self.initialize_settings(guild)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.initialize_settings(guild)

    async def initialize_settings(self, guild: discord.Guild):
        default_language = guild.preferred_locale.language_code if "COMMUNITY" in guild.features else "ko-KR"
        default_channel = getattr(guild.system_channel, "id", None)
        await self.database.upsert_settings(
            guild_id=guild.id,
            settings=GuildSettings(
                guild_id=guild.id, default_language=default_language, default_channel=default_channel
            ),
        )

    @app_commands.command(
        name=_T("settings", key="command.settings"), description=_T("description", key="command.settings.description")
    )
    @app_commands.default_permissions(administrator=True)
    async def settings(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        view = SettingsView(self.bot, interaction)
        await view.load()
        await interaction.followup.send(view=view)


async def setup(bot: Bot):
    await bot.add_cog(Settings(bot))
