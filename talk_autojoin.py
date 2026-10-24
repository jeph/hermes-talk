"""Auto-join one Discord voice channel and run Talk while an operator is in it.

Fork addition (jeph/hermes-talk; see FORK.md). With
``TALK_AUTOJOIN_VOICE_CHANNEL_ID`` set, the bot joins that channel and starts
the same session ``/talk join`` starts whenever a member listed in
``TALK_DISCORD_OPERATOR_USER_IDS`` is in it, and stops the session and leaves
once no operator remains. Unset, nothing is wired.

Wired through the host's ``register_platform_handler("discord", factory)``:
the factory receives the discord.py ``commands.Bot`` and the Discord adapter
once the client is ready, and ``add_listener`` keeps the host's own
``on_voice_state_update`` handler intact.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

try:
    from . import talk_config, talk_discord
except ImportError:  # pragma: no cover - flat-module fallback (pip -e install)
    import talk_config
    import talk_discord

_log = logging.getLogger(__name__)

CHANNEL_ENV = "TALK_AUTOJOIN_VOICE_CHANNEL_ID"


def channel_id() -> int | None:
    raw = (os.environ.get(CHANNEL_ENV) or "").strip()
    return int(raw) if raw.isdecimal() else None


def _session_live() -> bool:
    with talk_discord._SESSION_LOCK:
        task = talk_discord._SESSION.get("task")
    return task is not None and not task.done()


def _bot_in_channel(adapter: Any, guild_id: int, wanted: int) -> bool:
    voice_client = adapter._voice_clients.get(guild_id)
    return (
        voice_client is not None
        and voice_client.is_connected()
        and voice_client.channel.id == wanted
    )


def wire(bot: Any, adapter: Any) -> None:
    """Platform-handler factory: watch the configured channel on this client."""

    wanted = channel_id()
    if wanted is None:
        if os.environ.get(CHANNEL_ENV, "").strip():
            _log.warning("talk autojoin: %s is not a channel id; inactive", CHANNEL_ENV)
        return
    lock = asyncio.Lock()

    async def reconcile(guild: Any) -> None:
        async with lock:
            channel = guild.get_channel(wanted)
            if channel is None:
                return
            operators = talk_config.discord_operator_user_ids()
            operator_present = any(member.id in operators for member in channel.members)
            bot_here = _bot_in_channel(adapter, guild.id, wanted)
            live = _session_live()

            if operator_present and not live:
                if not bot_here and not await adapter.join_voice_channel(
                    channel, text_channel_id=wanted
                ):
                    _log.warning("talk autojoin: could not join voice channel %s", channel.name)
                    return
                result = talk_discord.start_session(guild.id)
                # start_session reports refusals as sentences, not exceptions.
                level = logging.INFO if result.startswith("Starting") else logging.WARNING
                _log.log(level, "talk autojoin: %s", result)
            elif not operator_present and bot_here:
                if live:
                    talk_discord.stop_session()
                await adapter.leave_voice_channel(guild.id)
                _log.info("talk autojoin: no operator in %s; left", channel.name)

    async def guarded_reconcile(guild: Any) -> None:
        try:
            await reconcile(guild)
        except Exception:  # noqa: BLE001 - a listener error must not reach discord.py's loop
            _log.exception("talk autojoin: reconcile failed")

    async def on_voice_state_update(member: Any, before: Any, after: Any) -> None:
        if member.bot:
            return
        touched = (getattr(before.channel, "id", None), getattr(after.channel, "id", None))
        if wanted in touched:
            await guarded_reconcile(member.guild)

    bot.add_listener(on_voice_state_update, "on_voice_state_update")

    # An operator may already be in the channel when the gateway (re)connects.
    channel = bot.get_channel(wanted)
    if channel is not None:
        try:
            asyncio.get_running_loop().create_task(guarded_reconcile(channel.guild))
        except RuntimeError:
            _log.info("talk autojoin: wired off-loop; waiting for the next voice state change")
    _log.info("talk autojoin: watching voice channel %s", wanted)


def register(ctx: Any) -> None:
    """Register the Discord factory when the host supports platform handlers."""

    register_handler = getattr(ctx, "register_platform_handler", None)
    if not callable(register_handler):
        _log.info("talk autojoin: host has no register_platform_handler; inactive")
        return
    register_handler("discord", wire)
