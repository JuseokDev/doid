#!/usr/bin/env python3
import asyncio
import logging
from pathlib import Path

import discord
import lavalink
from discord import app_commands
from discord.ext import commands

from database import Database
from logger import Formatter, get_formatter
from settings import settings
from translator import AppCommandTranslator

# fmt: off
EXTENSIONS = [
    "cogs.music",
    "cogs.misc",
    "cogs.settings"
]
# fmt: on

logger = logging.getLogger("bot")
logger.setLevel(logging.DEBUG)

stream_handler = logging.StreamHandler()
stream_handler.setLevel(logging.INFO)
stream_handler.setFormatter(get_formatter())
logger.addHandler(stream_handler)

log_path = Path("logs/bot.log")
log_path.parent.mkdir(parents=True, exist_ok=True)
file_handler = logging.FileHandler(log_path, encoding="utf-8")
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(Formatter())
logger.addHandler(file_handler)


class Bot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="/",
            help_command=None,
            allowed_contexts=app_commands.AppCommandContext(guild=True, dm_channel=False, private_channel=False),
            allowed_installs=app_commands.AppInstallationType(guild=True, user=False),
            intents=intents,
        )

        self.database = Database(
            host=settings.DATABASE_HOST,
            port=settings.DATABASE_PORT,
            username=settings.DATABASE_USERNAME,
            password=settings.DATABASE_PASSWORD,
            name=settings.DATABASE_NAME,
        )

        self.lavalink = None

        self.application_emojis: dict[str, str] = {}
        self.translator = AppCommandTranslator(self)

    async def setup_hook(self):
        self.lavalink = lavalink.Client(self.user.id)
        self.lavalink.add_node(
            settings.LAVALINK_HOST,
            settings.LAVALINK_PORT,
            settings.LAVALINK_PASSWORD,
            settings.LAVALINK_REGION,
            settings.LAVALINK_NAME,
        )

        await self.fetch_emojis()
        await self.tree.set_translator(self.translator)

        for extension in EXTENSIONS:
            try:
                await self.load_extension(extension)
                logger.info(f"[Cog] Successfully loaded: {extension}")
            except Exception:
                logger.exception(f"[Cog] Failed to load: {extension}")

        await self.tree.sync()

    async def on_message(self, message: discord.Message):
        pass

    async def close(self):
        tasks = [self.disconnect_voice(guild, force=True) for guild in self.guilds if guild.voice_client is not None]
        if tasks:
            await asyncio.gather(*tasks)

        for extension in tuple(self.extensions):
            try:
                await self.unload_extension(extension)
            except Exception:
                logger.exception(f"[Cog] Failed to unload: {extension}")

        try:
            await self.lavalink.close()
        except Exception:
            logger.exception("[Lavalink] Failed to close lavalink client")

        await self.database.close()
        await super().close()

    @staticmethod
    async def disconnect_voice(guild: discord.Guild, force: bool = False):
        if guild.voice_client is None:
            return

        voice = guild.me.voice
        if voice and voice.channel:
            try:
                await voice.channel.edit(status=None)
            except Exception:
                pass

        try:
            await guild.voice_client.disconnect(force=force)
        except Exception:
            pass

    async def reload(self):
        await self.fetch_emojis()
        await self.translator.reload()
        await self.tree.sync()

    async def fetch_emojis(self):
        emojis = await self.fetch_application_emojis()
        self.application_emojis = {emoji.name: f"<:{emoji.name}:{emoji.id}>" for emoji in emojis}


bot = Bot()


if __name__ == "__main__":
    bot.run(settings.BOT_TOKEN)
