#!/usr/bin/env python3
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from database import Database
from logger import Formatter, get_formatter
from settings import settings
from translator import Translator

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

        self.application_emojis: dict[str, str] = {}

    async def setup_hook(self):
        await self.fetch_emojis()
        await self.tree.set_translator(Translator(self))
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
        await self.database.close()
        await super().close()

    async def fetch_emojis(self):
        emojis = await self.fetch_application_emojis()
        self.application_emojis = {emoji.name: f"<:{emoji.name}:{emoji.id}>" for emoji in emojis}


bot = Bot()


if __name__ == "__main__":
    bot.run(settings.BOT_TOKEN)
