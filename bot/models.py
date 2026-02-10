from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from typing import Literal

from bson import ObjectId


@dataclass
class Track:
    author: str
    duration: int
    identifier: str
    requester: int
    source_name: str
    title: str
    track: str | None
    uri: str


@dataclass
class PlayCommandHistory:
    channel_id: int
    interaction_id: int
    message_id: int
    user_id: int
    query: str
    load_type: str
    tracks: list[Track]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _id: ObjectId = field(default_factory=ObjectId)

    @classmethod
    def from_dict(cls, data: dict):
        track_fields = fields(Track)
        tracks = [Track(**{f.name: getattr(t, f.name) for f in track_fields}) for t in data.get("tracks", [])]
        other_data = {k: v for k, v in data.items() if k != "tracks"}
        return cls(tracks=tracks, **other_data)


@dataclass
class PlaybackHistory:
    channel_id: int
    interaction_id: int
    message_id: int
    user_id: int
    identifier: str
    source_name: str
    track: str | None
    uri: str
    played_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _id: ObjectId = field(default_factory=ObjectId)

    @classmethod
    def from_dict(cls, data: dict):
        class_fields = {f.name for f in fields(cls)}
        filtered_data = {k: v for k, v in data.items() if k in class_fields}
        return cls(**filtered_data)


@dataclass
class QueryHistory:
    type: Literal["play", "search"]
    guild_id: int
    channel_id: int
    user_id: int
    query: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _id: ObjectId = field(default_factory=ObjectId)
