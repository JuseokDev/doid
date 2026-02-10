from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import Bot

DEFAULT_LOCALE = "ko-KR"

logger = logging.getLogger("bot.translator")


class Translator(app_commands.Translator):
    def __init__(self, bot: Bot, *, locale_dir: str = "locales", default_locale: str = DEFAULT_LOCALE):
        self.bot: Bot = bot
        self.locale_dir = Path(locale_dir)
        self.default_locale: str = default_locale
        self.emojis: dict[str, str] = self.bot.application_emojis
        self.emoji_pattern = re.compile(r":(\w+):")
        self._translations: dict[str, dict[str, str]] = {}

    @property
    def locales(self):
        return list(self._translations.keys())

    def _get(self, key: str, language_code: str) -> str | None:
        if language_code not in self.locales:
            return
        return self._translations.get(language_code).get(key)

    def _get_language_code(self, locale: discord.Locale) -> str:
        language_code = locale.language_code
        if language_code not in self.locales:
            return self.default_locale
        return language_code

    async def load(self):
        if not self.locale_dir.is_dir():
            logger.error(f"[Locale] Directory not found: {self.locale_dir}")
            return

        for path in self.locale_dir.glob("*.json"):
            lang = path.stem
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                self._translations[lang] = data
            except Exception:
                logger.exception(f"[Locale] Failed to load translations for {lang}")

        logger.info(f"[Locale] Successfully loaded {len(self.locales)} languages")

    def repl(self, match: re.Match) -> str:
        name = match.group(1)
        emoji = self.emojis.get(name)
        return emoji if emoji else match.group(0)

    def replace_emojis(self, text: str) -> str:
        return self.emoji_pattern.sub(self.repl, text)

    async def translate(
        self,
        string: app_commands.locale_str,
        locale: discord.Locale,
        context: app_commands.TranslationContext,
    ) -> str | None:
        extras = string.extras
        key = extras.get("key")

        if not key:
            return string.message

        lang = self._get_language_code(locale)

        translation = self._get(key, lang) or self._get(key, self.default_locale)
        if translation is None:
            logger.warning(f"[Translation] Missing translation key: {key}")
            return string.message

        translation = await asyncio.to_thread(self.replace_emojis, translation)

        try:
            translation = translation.format(**extras)
        except KeyError:
            logger.exception("[Translation] Failed to format: missing some key(s)")

        return translation
