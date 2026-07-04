"""Integration-style tests for EnvisalinkClient against a fake TPI TCP server.

Runs a real asyncio TCP server on localhost so the client exercises actual
socket I/O (framing, buffering, disconnects) rather than hand-mocked streams.
"""
from __future__ import annotations

import asyncio

import pytest

from custom_components.envisalink_field_programmer.client import (
    EnvisalinkClient,
    TPIAuthError,
    TPIConnectionError,
)

from .helpers import FakeEnvisalinkServer


@pytest.fixture
async def fake_server():
    server = FakeEnvisalinkServer()
    await server.start()
    yield server
    await server.stop()


async def test_successful_login_and_keepalive(fake_server):
    events = []
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "user", event_callback=events.append
    )
    await client.connect()
    try:
        assert client.connected
        await client.keep_alive()
        await asyncio.sleep(0.05)
        assert ("00", "") in fake_server.received
    finally:
        await client.disconnect()


async def test_wrong_password_raises_auth_error(fake_server):
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "wrong", event_callback=lambda e: None
    )
    with pytest.raises(TPIAuthError):
        await client.connect()


async def test_connection_refused_raises_connection_error():
    client = EnvisalinkClient(
        "127.0.0.1", 1, "user", event_callback=lambda e: None
    )
    with pytest.raises((TPIConnectionError, OSError)):
        await client.connect()


async def test_events_are_delivered_to_callback(fake_server):
    events = []
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "user", event_callback=events.append
    )
    await client.connect()
    try:
        await fake_server.push("00", "1,1020,0,08,ready")
        await asyncio.sleep(0.05)
        assert any(e.code == "%00" and e.fields.get("partition") == "1" for e in events)
    finally:
        await client.disconnect()


async def test_disconnect_callback_invoked_on_server_close(fake_server):
    disconnects = []
    client = EnvisalinkClient(
        "127.0.0.1",
        fake_server.port,
        "user",
        event_callback=lambda e: None,
        disconnect_callback=disconnects.append,
    )
    await client.connect()
    await fake_server.stop()
    await asyncio.sleep(0.1)
    assert len(disconnects) == 1


async def test_send_keystrokes_sends_one_character_per_frame(fake_server):
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "user", event_callback=lambda e: None
    )
    await client.connect()
    try:
        await client.send_keystrokes(1, "1234")
        await asyncio.sleep(0.05)
        keypress_frames = [d for c, d in fake_server.received if c == "03"]
        assert keypress_frames == ["1,1", "1,2", "1,3", "1,4"]
    finally:
        await client.disconnect()


async def test_dump_zone_timers_sends_expected_command(fake_server):
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "user", event_callback=lambda e: None
    )
    await client.connect()
    try:
        await client.dump_zone_timers()
        await asyncio.sleep(0.05)
        assert ("02", "") in fake_server.received
    finally:
        await client.disconnect()
