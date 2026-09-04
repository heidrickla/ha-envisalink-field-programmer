"""Unit tests for the raw TPI wire protocol: framing, sentinel-stripping,
and event field tokenizing. No Home Assistant or asyncio event loop
required for these -- pure functions.
"""

from __future__ import annotations

import pytest

from custom_components.envisalink_field_programmer.client import (
    TPIProtocolError,
    build_event,
    parse_frame,
    strip_leading_garbage,
)


def test_strip_leading_garbage_removes_bytes_before_sentinel():
    assert strip_leading_garbage("junk%00,1,a") == "%00,1,a"
    assert strip_leading_garbage("^03,1,4") == "^03,1,4"


def test_strip_leading_garbage_no_sentinel_returns_unchanged():
    assert strip_leading_garbage("nosentinelhere") == "nosentinelhere"


def test_parse_frame_splits_code_and_data():
    code, data = parse_frame("%00,1,10200,08,ready")
    assert code == "%00"
    assert data == "1,10200,08,ready"


def test_parse_frame_strips_leading_garbage_first():
    code, data = parse_frame("garbage%FF,ABCD")
    assert code == "%FF"
    assert data == "ABCD"


def test_parse_frame_rejects_short_frame():
    with pytest.raises(TPIProtocolError):
        parse_frame("%0")


def test_parse_frame_rejects_missing_comma():
    with pytest.raises(TPIProtocolError):
        parse_frame("%00xno-comma")


def test_build_event_keypad_update_tokenizes_fields():
    event = build_event("%00", "1,1020,0,08,ready")
    assert event.name == "keypad_update"
    assert event.fields["partition"] == "1"
    assert event.fields["icon_led_hex"] == "1020"
    assert event.fields["beep_hex"] == "08"
    assert event.fields["alpha"] == "ready"


def test_build_event_keypad_update_alpha_may_contain_commas():
    event = build_event("%00", "1,1000,08,00,ARMED, STAY")
    assert event.fields["alpha"] == "ARMED, STAY"


def test_build_event_realtime_cid_event_slices_fixed_width_fields():
    # qualifier=3 (closing/arm), cid_event=401, partition=01, user=005
    event = build_event("%03", "3401" + "01" + "005")
    assert event.name == "realtime_cid_event"
    assert event.fields["qualifier"] == "3"
    assert event.fields["cid_event"] == "401"
    assert event.fields["partition"] == "01"
    assert event.fields["zone_or_user"] == "005"


def test_build_event_zone_timer_dump_keeps_raw_hex():
    hex_string = "FFFF" * 64
    event = build_event("%FF", hex_string)
    assert event.name == "zone_timer_dump"
    assert event.raw_data == hex_string


def test_build_event_command_ack_extracts_response_code():
    event = build_event("^03", "00")
    assert event.name == "keypress_ack"
    assert event.fields["response_code"] == "00"


def test_build_event_unknown_code_has_name_unknown():
    event = build_event("%99", "whatever")
    assert event.name == "unknown"
    assert event.raw_data == "whatever"
