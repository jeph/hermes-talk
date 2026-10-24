"""Discord voice auto-join (fork addition, FORK.md): who triggers it and when it ends."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

import pytest

import talk_autojoin
import talk_discord

CHANNEL = 42
GUILD = 1
OPERATOR = 101
GUEST = 202


class FakeTask:
    def __init__(self):
        self.finished = False

    def done(self):
        return self.finished


class FakeVoiceClient:
    def __init__(self, channel):
        self.channel = channel

    def is_connected(self):
        return True


class Room:
    """A guild with one voice channel, an adapter, a bot, and a call log."""

    def __init__(self, monkeypatch, *, start_reply="Starting limited legacy voice."):
        self.calls: list[tuple] = []
        self.channel = NS(id=CHANNEL, name="Talk", members=[])
        self.guild = NS(id=GUILD, get_channel=lambda cid: self.channel if cid == CHANNEL else None)
        self.channel.guild = self.guild
        self.listeners: dict[str, object] = {}
        self.bot = NS(
            add_listener=lambda fn, name: self.listeners.setdefault(name, fn),
            get_channel=lambda cid: self.channel if cid == CHANNEL else None,
        )
        room = self

        class Adapter:
            def __init__(self):
                self._voice_clients: dict = {}

            async def join_voice_channel(self, channel, *, text_channel_id=None):
                room.calls.append(("join", channel.id, text_channel_id))
                self._voice_clients[GUILD] = FakeVoiceClient(channel)
                return True

            async def leave_voice_channel(self, guild_id):
                room.calls.append(("leave", guild_id))
                self._voice_clients.pop(guild_id, None)

        self.adapter = Adapter()
        session: dict = {}
        monkeypatch.setattr(talk_discord, "_SESSION", session)

        def start_session(guild_id):
            room.calls.append(("start", guild_id))
            if start_reply.startswith("Starting"):
                session["task"] = FakeTask()
            return start_reply

        def stop_session():
            room.calls.append(("stop",))
            session["task"].finished = True
            return "stopped"

        monkeypatch.setattr(talk_discord, "start_session", start_session)
        monkeypatch.setattr(talk_discord, "stop_session", stop_session)

    def member(self, user_id):
        return NS(id=user_id, bot=False, guild=self.guild)

    async def enter(self, user_id):
        member = self.member(user_id)
        self.channel.members.append(member)
        await self.listeners["on_voice_state_update"](
            member, NS(channel=None), NS(channel=self.channel)
        )

    async def exit(self, user_id):
        member = self.member(user_id)
        self.channel.members = [m for m in self.channel.members if m.id != user_id]
        await self.listeners["on_voice_state_update"](
            member, NS(channel=self.channel), NS(channel=None)
        )


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv(talk_autojoin.CHANNEL_ENV, str(CHANNEL))
    monkeypatch.setenv("TALK_DISCORD_OPERATOR_USER_IDS", str(OPERATOR))


def test_operator_presence_drives_join_start_stop_leave(monkeypatch, configured):
    room = Room(monkeypatch)

    async def scenario():
        talk_autojoin.wire(room.bot, room.adapter)
        await asyncio.sleep(0)
        assert room.calls == []

        await room.enter(GUEST)
        assert room.calls == [], "a non-operator must not start a paid session"

        await room.enter(OPERATOR)
        assert room.calls == [("join", CHANNEL, CHANNEL), ("start", GUILD)]

        await room.exit(GUEST)
        assert len(room.calls) == 2, "the operator is still present"

        await room.exit(OPERATOR)
        assert room.calls[2:] == [("stop",), ("leave", GUILD)]

        await room.enter(OPERATOR)
        assert room.calls[4:] == [("join", CHANNEL, CHANNEL), ("start", GUILD)]

    asyncio.run(scenario())


def test_operator_already_present_at_connect_is_joined(monkeypatch, configured):
    room = Room(monkeypatch)
    room.channel.members.append(room.member(OPERATOR))

    async def scenario():
        talk_autojoin.wire(room.bot, room.adapter)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert room.calls == [("join", CHANNEL, CHANNEL), ("start", GUILD)]


def test_other_channels_are_ignored(monkeypatch, configured):
    room = Room(monkeypatch)
    elsewhere = NS(id=CHANNEL + 1, name="Lounge", members=[])

    async def scenario():
        talk_autojoin.wire(room.bot, room.adapter)
        await room.listeners["on_voice_state_update"](
            room.member(OPERATOR), NS(channel=None), NS(channel=elsewhere)
        )

    asyncio.run(scenario())
    assert room.calls == []


def test_refused_start_is_logged_as_warning(monkeypatch, configured, caplog):
    room = Room(monkeypatch, start_reply="I'm not in a voice channel on that server")

    async def scenario():
        talk_autojoin.wire(room.bot, room.adapter)
        await room.enter(OPERATOR)

    with caplog.at_level("INFO", logger=talk_autojoin.__name__):
        asyncio.run(scenario())
    refusals = [r for r in caplog.records if "not in a voice channel" in r.getMessage()]
    # The connect-time reconcile and the join event can both attempt a start.
    assert refusals
    assert {r.levelname for r in refusals} == {"WARNING"}


@pytest.mark.parametrize("value", ["", "Talk", "-5"])
def test_unset_or_malformed_channel_wires_nothing(monkeypatch, value):
    monkeypatch.setenv(talk_autojoin.CHANNEL_ENV, value)
    room = Room(monkeypatch)

    talk_autojoin.wire(room.bot, room.adapter)

    assert room.listeners == {}
