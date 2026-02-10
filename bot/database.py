import logging
from dataclasses import asdict
from datetime import datetime, timezone

from pymongo import AsyncMongoClient
from pymongo.errors import ConnectionFailure

from models import PlaybackHistory, PlayCommandHistory, QueryHistory

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

    async def set_channel_volume(self, channel_id: int, volume: int):
        collection = self.database["channel_volumes"]
        await collection.update_one({"channel_id": channel_id}, {"$set": {"volume": volume}}, upsert=True)

    async def get_channel_volume(self, channel_id: int) -> int | None:
        collection = self.database["channel_volumes"]
        document = await collection.find_one({"channel_id": channel_id})
        if document is None:
            return None
        return document["volume"]

    async def set_default_volume(self, guild_id: int, volume: int):
        collection = self.database["default_volumes"]
        await collection.update_one({"guild_id": guild_id}, {"$set": {"volume": volume}}, upsert=True)

    async def get_default_volume(self, guild_id: int) -> int | None:
        collection = self.database["default_volumes"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["volume"]

    async def set_dedicated_channel(self, guild_id: int, channel_id: int):
        collection = self.database["dedicated_channels"]
        await collection.update_one(
            {"guild_id": guild_id},
            {"$set": {"channel_id": channel_id, "updated_at": datetime.now(timezone.utc)}},
            upsert=True,
        )

    async def get_dedicated_channel(self, guild_id: int) -> int | None:
        collection = self.database["dedicated_channels"]
        document = await collection.find_one({"guild_id": guild_id})
        if document is None:
            return None
        return document["channel_id"]

    async def get_dedicated_channels(self) -> dict[int, int]:
        dedicated_channels = {}
        collection = self.database["dedicated_channels"]
        async with collection.find() as cursor:
            async for document in cursor:
                dedicated_channels[document["guild_id"]] = document["channel_id"]
        return dedicated_channels

    async def insert_playback_history(self, history: PlaybackHistory):
        collection = self.database["playback_history"]
        await collection.insert_one(asdict(history))

    async def insert_play_command_history(self, history: PlayCommandHistory):
        collection = self.database["play_command_history"]
        await collection.insert_one(asdict(history))

    async def insert_query_history(self, history: QueryHistory):
        collection = self.database["query_history"]
        await collection.insert_one(asdict(history))
