import logging
from datetime import datetime, timezone

from pymongo import AsyncMongoClient

from models import GuildSettings, PlaybackHistory, PlayHistory, QueryHistory

logger = logging.getLogger("bot.database")
logger.setLevel(logging.WARNING)


class Database:
    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
        name: str = "database",
    ):
        self.client = AsyncMongoClient(host=host, port=port, username=username, password=password, authSource="admin")
        self.database = self.client.get_database(name)

    async def close(self):
        await self.client.close()

    async def upsert_settings(self, guild_id: int, settings: GuildSettings):
        collection = self.database["guild_settings"]
        await collection.update_one(
            {"guild_id": guild_id},
            {"$set": settings.to_dict()},
            upsert=True,
        )

    async def get_settings(self, guild_id: int) -> GuildSettings | None:
        collection = self.database["guild_settings"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return GuildSettings.from_dict(document)

    async def set_default_language(self, guild_id: int, language: str):
        collection = self.database["guild_settings"]
        await collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "default_language": language,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def get_default_language(self, guild_id: int) -> str | None:
        collection = self.database["guild_settings"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["default_language"]

    async def set_announcement_channel(self, guild_id: int, channel_id: int):
        collection = self.database["guild_settings"]
        await collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "announcement_channel": channel_id,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
            upsert=True,
        )

    async def get_announcement_channel(self, guild_id: int) -> int | None:
        collection = self.database["guild_settings"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["announcement_channel"]

    async def set_dedicated_channel(self, guild_id: int, channel_id: int):
        collection = self.database["guild_settings"]
        await collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "dedicated_channel": channel_id,
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

    async def get_dedicated_channel(self, guild_id: int) -> int | None:
        collection = self.database["guild_settings"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["dedicated_channel"]

    async def get_dedicated_channels(self) -> dict[int, int | None]:
        dedicated_channels = {}
        collection = self.database["guild_settings"]
        async with collection.find() as cursor:
            async for document in cursor:
                dedicated_channels[document["guild_id"]] = document["dedicated_channel"]
        return dedicated_channels

    async def set_default_volume(self, guild_id: int, volume: int):
        collection = self.database["guild_settings"]
        await collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "default_volume": volume,
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

    async def get_default_volume(self, guild_id: int) -> int | None:
        collection = self.database["guild_settings"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["default_volume"]

    async def set_maximum_volume(self, guild_id: int, volume: int):
        collection = self.database["guild_settings"]
        await collection.update_one(
            {"guild_id": guild_id},
            {
                "$set": {
                    "maximum_volume": volume,
                    "updated_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

    async def get_maximum_volume(self, guild_id: int) -> int | None:
        collection = self.database["guild_settings"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["maximum_volume"]

    async def set_channel_volume(self, channel_id: int, volume: int):
        collection = self.database["channel_volumes"]
        await collection.update_one(
            {"channel_id": channel_id},
            {
                "$set": {
                    "volume": volume,
                },
            },
            upsert=True,
        )

    async def get_channel_volume(self, channel_id: int) -> int | None:
        collection = self.database["channel_volumes"]
        document = await collection.find_one({"channel_id": channel_id})
        if document is None:
            return None
        return document["volume"]

    async def insert_playback_history(self, history: PlaybackHistory):
        collection = self.database["playback_history"]
        await collection.insert_one(history.to_dict())

    async def insert_play_history(self, history: PlayHistory):
        collection = self.database["play_history"]
        await collection.insert_one(history.to_dict())

    async def insert_query_history(self, history: QueryHistory):
        collection = self.database["query_history"]
        await collection.insert_one(history.to_dict())
