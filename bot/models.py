from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from typing import Literal

import lavalink
from bson import ObjectId

from settings import settings


class BaseDataclass:
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)

    def to_dict(self):
        return asdict(self)


@dataclass
class Track:
    author: str
    duration: int
    identifier: str
    isrc: str | None
    source_name: str
    title: str
    track: str | None
    uri: str

    @classmethod
    def from_track(cls, track: lavalink.AudioTrack):
        return cls(
            author=track.author,
            duration=track.duration,
            identifier=track.identifier,
            isrc=track.isrc,
            source_name=track.source_name,
            title=track.title,
            track=track.track,
            uri=track.uri,
        )


@dataclass
class PlayHistory(BaseDataclass):
    type: Literal["command", "message"]
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
        track_data = data.pop("tracks", [])
        tracks = [Track.from_track(track) for track in track_data]
        return cls(tracks=tracks, **data)


@dataclass
class PlaybackHistory(BaseDataclass):
    channel_id: int
    interaction_id: int
    message_id: int
    user_id: int
    track: Track
    played_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _id: ObjectId = field(default_factory=ObjectId)


@dataclass
class QueryHistory(BaseDataclass):
    type: Literal["play", "search"]
    guild_id: int
    channel_id: int
    user_id: int
    query: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _id: ObjectId = field(default_factory=ObjectId)


@dataclass(kw_only=True)
class GuildSettings(BaseDataclass):
    guild_id: int
    default_language: Literal["en-US", "ko-KR"] | None = None
    announcement_channel: int | None = None
    dedicated_channel: int | None = None
    default_volume: int = settings.DEFAULT_VOLUME
    maximum_volume: int | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    _id: ObjectId = field(default_factory=ObjectId)
