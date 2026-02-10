from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import discord
import lavalink
from discord import app_commands
from discord.app_commands import locale_str as _T
from discord.ext import commands
from discord.ui import Button, View
from lavalink.errors import ClientError
from lavalink.events import (
    NodeConnectedEvent,
    NodeDisconnectedEvent,
    QueueEndEvent,
    TrackStartEvent,
)
from lavalink.filters import Volume
from lavalink.server import LoadType

import utils
from models import PlaybackHistory, PlayCommandHistory
from settings import settings

if TYPE_CHECKING:
    from bot import Bot

DEFAULT_VOLUME = 100

logger = logging.getLogger("bot.music")


def has_available_nodes():
    async def predicate(interaction: discord.Interaction) -> bool:
        binding = interaction.command.binding
        if len(binding.lavalink.node_manager.available_nodes) == 0:
            await utils.send_message(interaction, "message.nodes.unavailable", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


def ensure_voice_state():
    async def predicate(interaction: discord.Interaction) -> bool:
        user_voice = interaction.user.voice
        if user_voice is None:
            await utils.send_message(interaction, "message.channel.join_first", ephemeral=True)
            return False
        voice = interaction.guild.me.voice
        if voice is not None and voice.channel.id != user_voice.channel.id:
            await utils.send_message(interaction, "message.channel.join_my_channel", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


def is_playing():
    async def predicate(interaction: discord.Interaction) -> bool:
        binding = interaction.command.binding
        player = binding.get_player(interaction.guild_id)
        if player is None:
            await utils.send_message(interaction, "message.player.not_playing", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


def can_join_voice_channel():
    async def predicate(interaction: discord.Interaction) -> bool:
        voice_channel = interaction.user.voice.channel
        permissions = voice_channel.permissions_for(interaction.guild.me)
        if not permissions.connect:
            await utils.send_message(interaction, "message.channel.missing_permissions", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


def is_channel_not_full():
    async def predicate(interaction: discord.Interaction) -> bool:
        voice = interaction.guild.me.voice
        if voice is not None:
            return True
        channel = interaction.user.voice.channel
        if 0 < channel.user_limit <= len(channel.members):
            await utils.send_message(interaction, "message.channel.full", ephemeral=True)
            return False
        return True

    return app_commands.check(predicate)


async def dynamic_cooldown(interaction: discord.Interaction) -> app_commands.Cooldown | None:
    binding = interaction.command.binding
    if await binding.bot.is_owner(interaction.user):
        return None
    if interaction.user.guild_permissions.administrator:
        return app_commands.Cooldown(10, 300)
    return app_commands.Cooldown(10, 600)


async def search_cooldown(interaction: discord.Interaction) -> app_commands.Cooldown | None:
    binding = interaction.command.binding
    if await binding.bot.is_owner(interaction.user):
        return None
    if interaction.user.guild_permissions.administrator:
        return app_commands.Cooldown(5, 300)
    return app_commands.Cooldown(5, 600)


class QueuedItemView(View):
    message: discord.Message

    def __init__(self, music: Music, requester_id: int, *, timeout=60):
        super().__init__(timeout=timeout)
        self.music = music
        self.requester_id = requester_id
        self.done = False
        self.lock = asyncio.Lock()

        emoji = music.bot.application_emojis.get("playlist_remove")
        button = Button(label="취소", emoji=emoji)
        button.callback = self.undo_enqueue
        self.add_item(button)

    async def on_timeout(self):
        if not self.message.components:
            return

        try:
            await self.message.edit(view=None)
        except:
            pass

    async def undo_enqueue(self, interaction: discord.Interaction):
        async with self.lock:
            if self.done:
                return

            permissions = interaction.user.guild_permissions
            if interaction.user.id != self.requester_id and not (
                permissions.administrator or permissions.move_members or permissions.mute_members
            ):
                await utils.send_message(interaction, "message.queue.cancel_unauthorized", ephemeral=True)
                return

            player = self.music.get_player(interaction.guild_id)
            if player is None:
                await interaction.response.defer()
                return

            message_id = interaction.message.id
            if player.queue and player.queue[0].extra.get("message_id") == message_id:
                duration = player.current.duration
                if player.position + 2500 > duration:
                    await utils.send_message(interaction, "message.queue.cancel_unavailable", ephemeral=True)
                    return

            player.queue = [track for track in player.queue if track.extra.get("message_id") != message_id]

            try:
                await interaction.message.delete()
            except Exception:
                pass
            finally:
                await utils.send_message(interaction, "message.queue.item_canceled", ephemeral=True, silent=True)

            self.done = True


class VoiceClient(discord.VoiceProtocol):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self.guild_id = channel.guild.id
        self._destroyed = False
        self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        await self.lavalink.voice_update_handler({"t": "VOICE_SERVER_UPDATE", "d": data})

    async def on_voice_state_update(self, data):
        channel_id = data["channel_id"]

        if not channel_id:
            await self._destroy()
            return

        self.channel = self.client.get_channel(int(channel_id))

        await self.lavalink.voice_update_handler({"t": "VOICE_STATE_UPDATE", "d": data})

    async def connect(
        self,
        *,
        timeout: float,
        reconnect: bool,
        self_deaf: bool = True,
        self_mute: bool = False,
    ):
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel, self_mute=self_mute, self_deaf=self_deaf)

    async def disconnect(self, *, force: bool = False):
        player = self.lavalink.player_manager.get(self.channel.guild.id)

        if not force and not player.is_connected:
            return

        await self.channel.guild.change_voice_state(channel=None)

        player.channel_id = None
        await self._destroy()

    async def _destroy(self):
        self.cleanup()

        if self._destroyed:
            return

        self._destroyed = True

        try:
            await self.lavalink.player_manager.destroy(self.guild_id)
        except ClientError:
            pass


class Music(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.database = self.bot.database
        if not hasattr(self.bot, "lavalink"):
            self.bot.lavalink = lavalink.Client(self.bot.user.id)
            self.bot.lavalink.add_node(
                settings.LAVALINK_HOST,
                settings.LAVALINK_PORT,
                settings.LAVALINK_PASSWORD,
                settings.LAVALINK_REGION,
                settings.LAVALINK_NAME,
            )
        self.lavalink = self.bot.lavalink
        self.lavalink.add_event_hooks(self)
        self._dedicated_channels: dict[int, int] = {}
        self._disconnect_tasks: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._loop = asyncio.get_event_loop()

    async def cog_load(self):
        self._dedicated_channels = await self.database.get_dedicated_channels()

    async def cog_unload(self):
        lavalink = self.bot.lavalink
        lavalink._event_hooks.clear()

        for guild_id, player in list(lavalink.players.items()):
            await self.cleanup_player(guild_id, player)

        try:
            await lavalink.close()
        except Exception:
            logger.exception("[Lavalink] Failed to close lavalink client")
        finally:
            del self.bot.lavalink

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CheckFailure):
            return
        logger.exception(error)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        await self.database.set_default_volume(guild.id, DEFAULT_VOLUME)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        self.cancel_disconnect_task(guild.id)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        guild_id = message.guild.id
        if guild_id not in self._dedicated_channels:
            return

        channel_id = message.channel.id
        if channel_id != self._dedicated_channels[guild_id]:
            return

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ):
        if member.bot and member.id != self.bot.user.id:
            return

        if member.bot:
            if before.channel is not None and after.channel is None:
                self.cancel_disconnect_task(before.channel.guild.id)
                await self.set_voice_channel_status(before.channel, None)
                return

            if before.channel is not None and after.channel is not None and before.channel.id != after.channel.id:
                player = self.get_player(after.channel.guild.id)
                if player is None:
                    return
                player.store("channel", after.channel.id)
                await player.set_pause(not utils.humans(after.channel))
                await self.set_voice_channel_status(before.channel, None)
                await self.set_voice_channel_status(after.channel, f"{player.current.title} 듣는 중")
            return

        if before.channel is not None:
            if not utils.humans(before.channel) and self.bot.user.id in [
                member.id for member in before.channel.members
            ]:
                player = self.get_player(before.channel.guild.id)
                if player is None:
                    return
                await player.set_pause(True)
                self.create_disconnect_task(before.channel.guild.id)

        if after.channel is not None:
            if len(utils.humans(after.channel)) == 1 and self.bot.user.id in [
                member.id for member in after.channel.members
            ]:
                player = self.get_player(after.channel.guild.id)
                if player is None:
                    return
                await player.set_pause(False)
                self.cancel_disconnect_task(after.channel.guild.id)

    @lavalink.listener(TrackStartEvent)
    async def on_track_start(self, event: TrackStartEvent):
        player = event.player
        current = player.current
        if current is None:
            logger.error("[TrackStartEvent] Player current track is None")
            return

        channel_id = current.extra["channel_id"]
        message_id = current.extra["message_id"]
        await self.database.insert_playback_history(
            PlaybackHistory(
                channel_id,
                current.extra["interaction_id"],
                message_id,
                current.requester,
                current.identifier,
                current.source_name,
                current.track,
                current.uri,
            )
        )

        channel = self.bot.get_channel(channel_id)
        if channel is not None:
            message = await channel.fetch_message(message_id)
            if message is not None and message.components:
                await message.edit(view=None)

        voice_channel_id = player.fetch("channel")
        voice_channel = self.bot.get_channel(voice_channel_id)
        if voice_channel is None:
            return
        await self.set_voice_channel_status(voice_channel, f"{player.current.title} 듣는 중")

    @lavalink.listener(QueueEndEvent)
    async def on_queue_end(self, event: QueueEndEvent):
        guild_id = event.player.guild_id
        guild = self.bot.get_guild(guild_id)

        if guild is not None:
            await guild.voice_client.disconnect(force=True)

    @lavalink.listener(NodeConnectedEvent)
    async def on_node_connected(self, event: NodeConnectedEvent):
        logger.info(f"[Node] {event.node.name} has been connected")

    @lavalink.listener(NodeDisconnectedEvent)
    async def on_node_disconnected(self, event: NodeDisconnectedEvent):
        logger.info(f"[Node] {event.node.name} has been disconnected")

    async def get_default_volume(self, guild: discord.Guild) -> int:
        volume = await self.database.get_default_volume(guild.id)
        if volume is None:
            await self.database.set_default_volume(guild.id, DEFAULT_VOLUME)
            return DEFAULT_VOLUME
        return volume

    async def get_volume(self, channel: discord.VoiceChannel | discord.StageChannel) -> int:
        volume = await self.database.get_channel_volume(channel.id)
        if volume is None:
            return await self.get_default_volume(channel.guild)
        return volume

    async def create_player(self, guild_id: int, region: str | None = None, node: lavalink.Node | None = None):
        player = self.lavalink.player_manager.create(guild_id, region=region, node=node)
        await player.set_filter(Volume(0.5))
        return player

    def get_player(self, guild_id: int):
        return self.lavalink.player_manager.get(guild_id)

    @staticmethod
    async def set_voice_channel_status(channel: discord.VoiceChannel | discord.StageChannel, status: str | None):
        try:
            await channel.edit(status=status)
        except Exception:
            logger.exception("[VoiceChannelStatus] Failed to set voice channel status")

    async def cleanup_player(self, guild_id: int, player: lavalink.DefaultPlayer):
        player.queue.clear()

        try:
            await player.stop()
        except Exception:
            logger.error("[Player] Failed to stop player")

        guild = self.bot.get_guild(guild_id)
        if not (guild and guild.me.voice):
            return

        try:
            await self.set_voice_channel_status(guild.me.voice.channel, None)
            await guild.voice_client.disconnect(force=True)
        except Exception:
            logger.error("[VoiceClient] Failed to disconnect voice client")

    def create_disconnect_task(self, guild_id: int):
        dt = datetime.now() + timedelta(minutes=5)
        task = self._loop.create_task(self._disconnect(dt, guild_id))
        self._disconnect_tasks[guild_id] = task

    def cancel_disconnect_task(self, guild_id: int):
        if guild_id not in self._disconnect_tasks:
            return
        self._disconnect_tasks.get(guild_id).cancel()

    async def _disconnect(self, dt: datetime, guild_id: int):
        delay = (dt - datetime.now()).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)

        guild = self.bot.get_guild(guild_id)
        if guild is None:
            logger.error("[AutoDisconnect] Guild not found")
            return

        try:
            await guild.voice_client.disconnect()
        except Exception:
            logger.exception("[AutoDisconnect] Failed to disconnect voice client automatically")

    def get_lock(self, guild_id: int) -> asyncio.Lock:
        if guild_id not in self._locks:
            self._locks[guild_id] = asyncio.Lock()
        return self._locks[guild_id]

    @app_commands.command(
        name=_T("play", key="command.play"),
        description=_T("description", key="command.play.description"),
    )
    @app_commands.rename(query=_T("query", key="option.play.query"))
    @app_commands.describe(query=_T("description", key="option.play.query.description"))
    @app_commands.default_permissions(connect=True)
    @is_channel_not_full()
    @can_join_voice_channel()
    @ensure_voice_state()
    @has_available_nodes()
    @app_commands.checks.bot_has_permissions(connect=True, speak=True)
    @app_commands.checks.dynamic_cooldown(dynamic_cooldown, key=lambda i: (i.guild_id, i.user.id))
    async def play(self, interaction: discord.Interaction, query: str):
        response = await interaction.response.defer(thinking=True)
        lock = self.get_lock(interaction.guild_id)
        async with lock:
            player = await self.create_player(interaction.guild_id)
            original_query = query
            if utils.is_url(query.strip("<>")):
                query = query.strip("<>")
            else:
                query = f"ytsearch:{query}"
            results = await player.node.get_tracks(query)
            if results.load_type == LoadType.EMPTY:
                if not player.is_playing and not player.queue:
                    await player.destroy()
                await utils.send_message(interaction, "message.play.not_found", query=original_query)
                return
            elif results.load_type == LoadType.ERROR:
                await utils.send_message(interaction, "message.play.load_failed")
                logger.error(f"[Play] Failed to load result: {results.error.message}")
                return

            voice = interaction.guild.me.voice
            voice_channel = interaction.user.voice.channel
            if voice is None:
                await voice_channel.connect(cls=VoiceClient, self_deaf=True)
                player.store("channel", voice_channel.id)

            if results.load_type == LoadType.TRACK or results.load_type == LoadType.SEARCH:
                tracks = [results.tracks[0]]
            elif results.load_type == LoadType.PLAYLIST:
                tracks = results.tracks

            for track in tracks:
                track.extra["query"] = original_query
                track.extra["interaction_id"] = response.id
                track.extra["message_id"] = response.message_id
                track.extra["channel_id"] = interaction.channel_id
                track.extra["locale"] = interaction.locale

                player.add(track, requester=interaction.user.id)

            name = results.playlist_info.name if results.load_type == LoadType.PLAYLIST else track.title
            if player.is_playing:
                key = f"message.queue.{'playlist' if results.load_type == LoadType.PLAYLIST else 'track'}_added"
                view = QueuedItemView(self, interaction.user.id)
                view.message = await utils.send_message(interaction, key, view=view, name=name)
            else:
                key = f"message.play.{'playlist' if results.load_type == LoadType.PLAYLIST else 'track'}"
                await utils.send_message(interaction, key, name=name)

            if not player.is_playing:
                volume = await self.get_volume(voice_channel)
                if volume == 100:
                    await player.play()
                else:
                    await player.play(volume=volume)

            await self.database.insert_play_command_history(
                PlayCommandHistory.from_dict(
                    {
                        "channel_id": interaction.channel_id,
                        "interaction_id": interaction.id,
                        "message_id": response.message_id,
                        "user_id": interaction.user.id,
                        "query": original_query,
                        "load_type": "playlist" if results.load_type == LoadType.PLAYLIST else "track",
                        "tracks": tracks,
                    }
                )
            )

    @play.error
    async def on_play_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.BotMissingPermissions):
            permissions = ", ".join(
                [
                    f"`{await interaction.translate(_T(permission, key=f'permission.{permission}'), locale=interaction.locale)}`"
                    for permission in error.missing_permissions
                ]
            )
            await utils.send_message(
                interaction, "message.missing_permissions", ephemeral=True, permissions=permissions
            )
        elif isinstance(error, app_commands.CommandOnCooldown):
            remaining_time = str(timedelta(seconds=int(error.retry_after))).removeprefix("0:")
            await utils.send_message(interaction, "message.cooldown", ephemeral=True, remaining_time=remaining_time)
        elif isinstance(error, app_commands.CheckFailure):
            pass
        else:
            logger.exception("[Play] Error occurred during play command")

    @app_commands.command(
        name=_T("search", key="command.search"), description=_T("description", key="command.search.description")
    )
    @app_commands.rename(query=_T("query", key="option.search.query"))
    @app_commands.describe(query=_T("description", key="option.search.query.description"))
    @app_commands.default_permissions(connect=True)
    @app_commands.checks.bot_has_permissions(connect=True, speak=True)
    @app_commands.checks.dynamic_cooldown(search_cooldown, key=lambda i: (i.guild_id, i.user.id))
    @is_channel_not_full()
    @can_join_voice_channel()
    @ensure_voice_state()
    @has_available_nodes()
    async def search(self, interaction: discord.Interaction, query: str):
        pass

    @app_commands.command(
        name=_T("skip", key="command.skip"), description=_T("description", key="command.skip.description")
    )
    @is_playing()
    @ensure_voice_state()
    @has_available_nodes()
    async def skip(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        permissions = interaction.user.guild_permissions
        if (
            player.current.requester == interaction.user.id
            or permissions.administrator
            or permissions.move_members
            or permissions.mute_members
            or await self.bot.is_owner(interaction.user)
        ):
            await player.skip()
            await utils.send_message(interaction, "message.player.skipped")
        else:
            await utils.send_message(interaction, "message.skip.no_permission", ephemeral=True)

    @app_commands.command(
        name=_T("pause", key="command.pause"), description=_T("description", key="command.pause.description")
    )
    @is_playing()
    @ensure_voice_state()
    @has_available_nodes()
    async def pause(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        if not player.paused:
            await player.set_pause(True)
            await utils.send_message(interaction, "message.player.paused")
        else:
            await utils.send_message(interaction, "message.player.already_paused", ephemeral=True)

    @app_commands.command(
        name=_T("resume", key="command.resume"), description=_T("description", key="command.resume.description")
    )
    @is_playing()
    @ensure_voice_state()
    @has_available_nodes()
    async def resume(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        if player.paused:
            await player.set_pause(False)
            await utils.send_message(interaction, "message.player.resumed")
        else:
            await utils.send_message(interaction, "message.player.not_paused", ephemeral=True)

    @app_commands.command(
        name=_T("stop", key="command.stop"), description=_T("description", key="command.stop.description")
    )
    @is_playing()
    @ensure_voice_state()
    @has_available_nodes()
    async def stop(self, interaction: discord.Interaction):
        player = self.get_player(interaction.guild_id)
        player.queue.clear()
        await player.stop()
        await interaction.guild.voice_client.disconnect()
        await utils.send_message(interaction, "message.player.stopped")

    @app_commands.command(
        name=_T("volume", key="command.volume"), description=_T("description", key="command.volume.description")
    )
    @app_commands.rename(level=_T("level", key="option.level"))
    @app_commands.describe(level=_T("description", key="option.level.description"))
    @is_playing()
    @ensure_voice_state()
    @has_available_nodes()
    async def volume(
        self, interaction: discord.Interaction, level: app_commands.Range[int, 0, settings.MAX_VOLUME] | None = None
    ):
        player = self.get_player(interaction.guild_id)
        if level is None:
            if player.volume > 0:
                emoji = self.bot.application_emojis.get("volume_up" if player.volume >= 50 else "volume_down")
                await utils.send_message(interaction, "message.volume.current_level", emoji=emoji, level=player.volume)
            else:
                await utils.send_message(interaction, "message.player.muted")
            return

        if player.volume == level:
            await utils.send_message(interaction, "message.player.same_volume", ephemeral=True, level=level)
            return

        await player.set_volume(level)

        if level >= 10:
            await self.database.set_channel_volume(player.channel_id, level)

        emoji = self.bot.application_emojis.get("volume_up" if level >= 50 else "volume_down")
        await utils.send_message(interaction, "message.player.set_volume", emoji=emoji, level=level)

    @app_commands.command(
        name=_T("dedicated-channel", key="command.dedicated_channel"),
        description=_T("description", key="command.dedicated_channel.description"),
    )
    @app_commands.rename(channel=_T("channel", key="option.channel"))
    @app_commands.describe(channel=_T("description", key="option.channel.description"))
    @app_commands.default_permissions(manage_channels=True)
    async def dedicated_channel(self, interaction: discord.Interaction, channel: discord.TextChannel | None = None):
        guild_id = interaction.guild_id
        if channel is None:
            if interaction.guild_id not in self._dedicated_channels:
                await utils.send_message(interaction, "message.dedicated_channel.not_configured", ephemeral=True)
                return
            channel_id = self._dedicated_channels[guild_id]
            text_channel = self.bot.get_channel(channel_id)
            if text_channel is None:
                await utils.send_message(interaction, "message.dedicated_channel.not_found", ephemeral=True)
                return
            await utils.send_message(interaction, "message.dedicated_channel.current", channel=text_channel.mention)
            return
        self._dedicated_channels[guild_id] = channel.id
        await self.database.set_dedicated_channel(guild_id, channel.id)
        await utils.send_message(interaction, "message.dedicated_channel.updated", channel=channel.mention)


async def setup(bot: Bot):
    await bot.add_cog(Music(bot))
