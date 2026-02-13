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


class Translator:
    def __init__(self, bot: Bot, *, default_locale: str = DEFAULT_LOCALE, locale_dir: str | Path = "locales"):
        self.bot: Bot = bot
        self.default_locale = default_locale
        self.locale_dir = Path(locale_dir)
        self.emoji_pattern = re.compile(r":(\w+):")
        self.translations: dict[str, dict[str, str]] = {}
        self.loaded_event = asyncio.Event()

    @property
    def emojis(self) -> dict[str, str]:
        emojis = getattr(self.bot, "application_emojis", {})
        return emojis

    @property
    def locales(self) -> list[str]:
        return list(self.translations.keys())

    async def load(self):
        if not self.locale_dir.is_dir():
            logger.error(f"[Locale] Locale directory not found: {self.locale_dir}")
            self.loaded_event.set()
            return

        for path in self.locale_dir.glob("*.json"):
            lang = path.stem
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                self.translations[lang] = data
            except Exception:
                logger.exception(f"[Locale] Failed to load translations for {lang}")

        self.loaded_event.set()
        logger.info(f"[Locale] Successfully loaded {len(self.locales)} languages")

    async def reload(self):
        self.loaded_event.clear()
        self.translations.clear()
        await self.load()

    def get(self, key: str, lang: str) -> str | None:
        if lang not in self.translations:
            return None

        return self.translations.get(lang, {}).get(key)

    def get_lang(self, code: str) -> str:
        if code not in self.locales:
            return self.default_locale

        return code

    def repl(self, match: re.Match) -> str:
        name = match.group(1)
        emoji = self.emojis.get(name)
        return emoji if emoji else match.group(0)

    def replace_emojis(self, text: str) -> str:
        return self.emoji_pattern.sub(self.repl, text)

    async def translate(self, key: str, lang: str, **kwargs) -> str | None:
        if not key:
            logger.warning(f"[Translation] Key cannot be empty")
            return None

        await self.loaded_event.wait()

        lang = self.get_lang(lang)

        translation = self.get(key, lang) or self.get(key, self.default_locale)
        if translation is None:
            logger.warning(f"[Translation] Missing translation for key: {key}")
            return None

        translation = self.replace_emojis(translation)

        try:
            translation = translation.format(**kwargs)
        except KeyError as e:
            logger.error(f"[Translation] Missing required argument: {e.args[0]}")

        return translation


class AppCommandTranslator(Translator, app_commands.Translator):
    def __init__(self, bot: Bot, *, default_locale: str = DEFAULT_LOCALE, locale_dir: str | Path = "locales"):
        super().__init__(bot, default_locale=default_locale, locale_dir=locale_dir)

    async def load(self):
        await super().load()

    async def reload(self):
        await super().reload()

    async def translate(
        self, string: app_commands.locale_str, locale: discord.Locale, context: app_commands.TranslationContext
    ) -> str | None:
        extras = dict(string.extras)
        key = extras.pop("key") if "key" in extras else ""

        translation = await super().translate(key, locale.language_code, **extras)
        if translation is None:
            return string.message

        return translation
