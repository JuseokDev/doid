from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.app_commands import locale_str as _T
from discord.ext import commands
from discord.ui import (
    ActionRow,
    Button,
    ChannelSelect,
    Container,
    LayoutView,
    Select,
    Separator,
    TextDisplay,
)

import utils
from models import GuildSettings

if TYPE_CHECKING:
    from bot import Bot

logger = logging.getLogger("bot.settings")


class BaseItem:
    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__()
        self.bot: Bot = bot
        self.database = self.bot.database
        self.guild_id = interaction.guild_id
        self.locale = interaction.locale

    async def load(self):
        pass

    async def translate(self, key: str, **kwargs) -> str | None:
        return await self.bot.translator.translate(_T("", key=key, **kwargs), self.locale)


class BaseContainer(BaseItem, Container):
    async def add_text(self, key: str, **kwargs):
        text = await self.translate(key, **kwargs)
        self.add_item(TextDisplay(text))


class BaseDropdown(BaseItem, Select):
    pass


class BaseChannelDropdown(BaseItem, ChannelSelect):
    pass


class DefaultLanguageDropdown(BaseDropdown):
    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__(bot, interaction)

        self.min_values = 1
        self.max_values = 1

        self.languages = [
            ("english", "en-US"),
            ("korean", "ko-KR"),
        ]

    async def load(self):
        self.placeholder = await self.translate("settings.default_language.placeholder")
        default_language = await self.database.get_default_language(self.guild_id)
        self.options = [
            discord.SelectOption(
                label=await self.translate(f"language.{language}"),
                value=value,
                description=await self.translate(f"language.{language}.description"),
                default=(value == default_language),
            )
            for language, value in self.languages
        ]

    async def callback(self, interaction: discord.Interaction):
        await self.database.set_default_language(self.guild_id, self.values[0])
        await interaction.response.defer()


class DefaultLanguage(ActionRow):
    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__()

        self.dropdown = DefaultLanguageDropdown(bot, interaction)
        self.add_item(self.dropdown)

    async def load(self):
        await self.dropdown.load()


class AnnouncementChannelDropdown(BaseChannelDropdown):
    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__(bot, interaction)

        self.channel_types = [discord.ChannelType.text]
        self.min_values = 0
        self.max_values = 1

    async def load(self):
        self.placeholder = await self.translate("settings.announcement_channel.placeholder")
        announcement_channel = await self.database.get_announcement_channel(self.guild_id)
        if announcement_channel is not None:
            self.default_values = [discord.Object(announcement_channel)]

    async def callback(self, interaction: discord.Interaction):
        channel_id = self.values[0] if self.values else None
        await self.database.set_announcement_channel(self.guild_id, channel_id)
        await interaction.response.defer()


class AnnouncementChannel(ActionRow):
    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__()

        self.dropdown = AnnouncementChannelDropdown(bot, interaction)
        self.add_item(self.dropdown)

    async def load(self):
        await self.dropdown.load()


class GeneralSettings(BaseContainer):
    name = "general"

    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__(bot, interaction)

        self.default_language = DefaultLanguage(bot, interaction)
        self.announcement_channel = AnnouncementChannel(bot, interaction)

    async def load(self):
        await self.default_language.load()
        await self.announcement_channel.load()

        await self.add_text("settings.general")

        await self.add_text("settings.default_language")
        await self.add_text("settings.default_language.description")
        self.add_item(self.default_language)
        self.add_item(Separator())

        await self.add_text("settings.announcement_channel")
        await self.add_text("settings.announcement_channel.description")
        self.add_item(self.announcement_channel)


class VolumeSettings(BaseContainer):
    name = "volume"

    def __init__(self, bot: Bot, interaction: discord.Interaction):
        super().__init__(bot, interaction)

    async def load(self):
        pass


class SettingsView(LayoutView):
    message: discord.Message

    def __init__(self, bot: Bot, interaction: discord.Interaction, *, timeout=60):
        super().__init__(timeout=timeout)
        self.user_id = interaction.user.id
        self.containers: list[BaseContainer] = [
            GeneralSettings(bot, interaction),
        ]

    async def load(self):
        for container in self.containers:
            await container.load()

        self.add_item(self.containers[0])

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await utils.send_message(interaction, "message.settings.access_denied", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        try:
            await self.message.delete()
        except Exception:
            pass


class Settings(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.database = self.bot.database
        self.messages: dict[int, discord.Message] = {}

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
        announcement_channel = getattr(guild.system_channel, "id", None)
        await self.database.upsert_settings(
            guild_id=guild.id,
            settings=GuildSettings(
                guild_id=guild.id, default_language=default_language, announcement_channel=announcement_channel
            ),
        )

    async def delete_previous_message(self, guild_id: int):
        if guild_id not in self.messages:
            return

        try:
            await self.messages.get(guild_id).delete()
        except Exception:
            pass

    @app_commands.command(
        name=_T("settings", key="command.settings"), description=_T("description", key="command.settings.description")
    )
    @app_commands.default_permissions(administrator=True)
    async def settings(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await self.delete_previous_message(interaction.guild_id)
        view = SettingsView(self.bot, interaction)
        await view.load()
        message = await interaction.followup.send(view=view)
        view.message = message
        self.messages[interaction.guild_id] = message


async def setup(bot: Bot):
    await bot.add_cog(Settings(bot))
