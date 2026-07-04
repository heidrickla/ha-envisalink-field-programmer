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


async def test_successful_login_and_status_report(fake_server):
    events = []
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "user", event_callback=events.append
    )
    await client.connect()
    try:
        assert client.connected
        await client.status_report()
        await asyncio.sleep(0.05)
        assert ("001", "") in fake_server.received
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
        await fake_server.push("650", "1")
        await asyncio.sleep(0.05)
        assert any(e.code == "650" and e.partition == 1 for e in events)
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


async def test_send_keystrokes_chunks_into_frames_of_six(fake_server):
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "user", event_callback=lambda e: None
    )
    await client.connect()
    try:
        await client.send_keystrokes(1, "1234567890")
        await asyncio.sleep(0.05)
        keystroke_frames = [d for c, d in fake_server.received if c == "071"]
        assert keystroke_frames == ["1123456", "17890"]
    finally:
        await client.disconnect()
