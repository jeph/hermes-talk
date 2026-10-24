"""Native voice pace and speaking style (fork addition, FORK.md)."""

from __future__ import annotations

import pytest

import talk_config
import talk_wire


def _payload(**kwargs):
    return talk_wire.build_session_payload(model="m", voice="cedar", instructions="hi", **kwargs)


def test_unset_knobs_leave_the_session_unchanged(monkeypatch):
    monkeypatch.delenv("TALK_SPEED", raising=False)
    monkeypatch.delenv("TALK_VOICE_STYLE", raising=False)

    payload = _payload()

    assert payload["audio"]["output"] == {"voice": "cedar"}
    assert payload["instructions"] == "hi"


@pytest.mark.parametrize("raw,expected", [("1.5", 1.5), ("0.25", 0.25), (" 1.2 ", 1.2)])
def test_speed_rides_the_audio_output(monkeypatch, raw, expected):
    monkeypatch.setenv("TALK_SPEED", raw)

    assert _payload()["audio"]["output"] == {"voice": "cedar", "speed": expected}


@pytest.mark.parametrize("raw", ["1.51", "0.2", "fast"])
def test_out_of_range_or_junk_speed_refuses_instead_of_clamping(monkeypatch, raw):
    monkeypatch.setenv("TALK_SPEED", raw)

    with pytest.raises(talk_config.TalkConfigError, match="TALK_SPEED"):
        _payload()


def test_style_leads_the_instructions(monkeypatch):
    monkeypatch.setenv("TALK_VOICE_STYLE", "Speak with a British accent.")

    assert _payload()["instructions"] == "# Speaking style\nSpeak with a British accent.\n\nhi"


def test_text_output_sessions_ignore_both_knobs(monkeypatch):
    monkeypatch.setenv("TALK_SPEED", "1.5")
    monkeypatch.setenv("TALK_VOICE_STYLE", "Speak with a British accent.")

    payload = _payload(text_output=True)

    assert "output" not in payload["audio"]
    assert payload["instructions"] == "hi"
