"""Unit tests for the raw TPI wire protocol: checksum, framing, event parsing.

No Home Assistant or asyncio event loop required for these -- pure functions.
"""
from __future__ import annotations

import pytest

from custom_components.vista_console.client import (
    TPIProtocolError,
    build_event,
    compute_checksum,
    parse_frame,
)


def test_checksum_matches_spec_example():
    # From the TPI doc worked example: "6543" -> checksum D2.
    assert compute_checksum("6543") == "D2"


def test_checksum_wraps_at_8_bits():
    # Sum of a long run of characters must truncate to one byte.
    payload = "0" * 300
    checksum = compute_checksum(payload)
    assert len(checksum) == 2
    assert int(checksum, 16) <= 0xFF


def test_parse_frame_roundtrip():
    payload = "030" + "1"
    checksum = compute_checksum(payload)
    line = f"{payload}{checksum}"
    code, data = parse_frame(line)
    assert code == "030"
    assert data == "1"


def test_parse_frame_rejects_bad_checksum():
    with pytest.raises(TPIProtocolError):
        parse_frame("030199")


def test_parse_frame_rejects_short_frame():
    with pytest.raises(TPIProtocolError):
        parse_frame("01")


def test_build_event_zone_alarm():
    event = build_event("601", "1005")
    assert event.name == "zone_alarm"
    assert event.partition == 1
    assert event.zone == 5


def test_build_event_partition_armed_mode():
    event = build_event("652", "13")
    assert event.partition == 1
    assert event.fields["mode"] == "3"


def test_build_event_unknown_code_has_empty_fields():
    event = build_event("999", "abc")
    assert event.name == "unknown"
    assert event.fields == {}
    assert event.raw_data == "abc"


def test_build_event_zero_data_command():
    event = build_event("680", "")
    assert event.name == "system_in_installers_mode"
    assert event.fields == {}
