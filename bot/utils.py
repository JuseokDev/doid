import logging
import os
import re
from urllib.parse import urlparse

import discord
from discord.app_commands import locale_str
from discord.enums import InteractionResponseType
from discord.utils import MISSING

URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)

logger = logging.getLogger("bot.utils")
logger.setLevel(logging.WARNING)


async def send_message(
    interaction: discord.Interaction, key: str, *, view=MISSING, ephemeral: bool = False, silent: bool = False, **kwargs
):
    content = await interaction.translate(locale_str("", key=key, **kwargs), locale=interaction.locale)
    if not interaction.response.is_done():
        return await interaction.response.send_message(content, view=view, ephemeral=ephemeral, silent=silent)
    else:
        if interaction.response.type == InteractionResponseType.deferred_channel_message and ephemeral is True:
            logger.warning("The ephemeral parameter is not supported for deferred interaction webhook messages")
        return await interaction.followup.send(content, view=view, ephemeral=ephemeral, silent=silent)


def humans(channel: discord.VoiceChannel | discord.StageChannel) -> list[discord.Member]:
    return [member for member in channel.members if not member.bot]


def is_url(url: str) -> bool:
    return URL_PATTERN.match(url.strip("<>")) is not None


def get_filename(url: str) -> str:
    return os.path.basename(urlparse(url).path)
