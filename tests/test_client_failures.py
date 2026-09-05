"""Every way the TPI session can go wrong before or after the handshake.

The login is plain text over a raw socket, so each failure is scripted by a
tiny server that answers with exactly the bytes being tested.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from tests import pure
from tests.helpers import FakeEnvisalinkServer

client_module = pure.load("client")
EnvisalinkClient = client_module.EnvisalinkClient
TPIAuthError = client_module.TPIAuthError
TPIConnectionError = client_module.TPIConnectionError
TPIProtocolError = client_module.TPIProtocolError

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


class _ScriptedServer:
    """Answers one connection with whatever the handler writes."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self._server: asyncio.AbstractServer | None = None
        self.port = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handler, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()


async def _connect_to(handler: Handler) -> None:
    """Run the client's connect() against a scripted server."""
    server = _ScriptedServer(handler)
    await server.start()
    try:
        client = EnvisalinkClient(
            "127.0.0.1", server.port, "user", event_callback=lambda event: None
        )
        await client.connect()
    finally:
        await server.stop()


async def test_a_socket_that_closes_before_the_prompt_is_a_connection_error():
    async def _handler(reader, writer):
        writer.close()

    with pytest.raises(TPIConnectionError, match="before login prompt"):
        await _connect_to(_handler)


async def test_something_that_is_not_an_envisalink_is_a_connection_error():
    async def _handler(reader, writer):
        writer.write(b"SSH-2.0-OpenSSH_9.6\r\n")
        await writer.drain()

    with pytest.raises(TPIConnectionError, match="login prompt"):
        await _connect_to(_handler)


async def test_a_socket_that_closes_after_the_prompt_is_a_connection_error():
    # The prompt also arrives without its line ending, which the reader
    # recovers from the partial read.
    async def _handler(reader, writer):
        writer.write(b"Login:")
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    with pytest.raises(TPIConnectionError, match="during login"):
        await _connect_to(_handler)


async def test_the_envisalink_reporting_a_login_timeout_is_a_connection_error():
    async def _handler(reader, writer):
        writer.write(b"Login:\r\n")
        await writer.drain()
        await reader.readuntil(b"\r\n")
        writer.write(b"Timed Out!\r\n")
        await writer.drain()
        await asyncio.sleep(0.05)

    with pytest.raises(TPIConnectionError, match="timed out"):
        await _connect_to(_handler)


async def test_an_unrecognised_login_answer_is_a_connection_error():
    async def _handler(reader, writer):
        writer.write(b"Login:\r\n")
        await writer.drain()
        await reader.readuntil(b"\r\n")
        writer.write(b"MAYBE\r\n")
        await writer.drain()
        await asyncio.sleep(0.05)

    with pytest.raises(TPIConnectionError, match="unexpected login result"):
        await _connect_to(_handler)


async def test_a_login_line_that_never_ends_is_a_protocol_error():
    # A stream with no line ending would otherwise buffer without limit.
    async def _handler(reader, writer):
        writer.write(b"x" * 200_000)
        await writer.drain()
        await asyncio.sleep(0.05)

    with pytest.raises(TPIProtocolError, match="buffer limit"):
        await _connect_to(_handler)


async def test_a_command_waiting_on_its_ack_fails_when_the_session_goes():
    # Otherwise the caller waits out the whole acknowledgement timeout for a
    # socket that is already gone.
    server = FakeEnvisalinkServer()
    await server.start()
    server.ack_commands = False
    try:
        client = EnvisalinkClient(
            "127.0.0.1", server.port, "user", event_callback=lambda event: None
        )
        await client.connect()
        pending = asyncio.ensure_future(client.keep_alive())
        await asyncio.sleep(0.05)
        await client.disconnect()
        with pytest.raises(TPIConnectionError, match="disconnected"):
            await pending
    finally:
        await server.stop()


async def test_a_read_failure_reaches_the_disconnect_callback():
    """A broken read must tell the coordinator, not die silently in the task."""

    class _Reader:
        def __init__(self) -> None:
            self._lines = [b"Login:\r\n", b"OK\r\n"]

        async def readuntil(self, separator: bytes) -> bytes:
            return self._lines.pop(0)

        async def read(self, count: int) -> bytes:
            raise RuntimeError("the socket went away")

    class _Writer:
        def write(self, data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

        def is_closing(self) -> bool:
            return False

    async def _open(host: str, port: int):
        return _Reader(), _Writer()

    seen: list[Exception | None] = []
    client = EnvisalinkClient(
        "127.0.0.1",
        4025,
        "user",
        event_callback=lambda event: None,
        disconnect_callback=seen.append,
        open_connection=_open,
    )
    await client.connect()
    await asyncio.sleep(0.05)
    assert len(seen) == 1
    assert isinstance(seen[0], RuntimeError)


def test_empty_and_malformed_frames_are_dropped_without_stopping_the_stream():
    events: list[object] = []
    client = EnvisalinkClient("127.0.0.1", 4025, "user", event_callback=events.append)
    # An empty frame (the stray terminator a keybus glitch can leave), a frame
    # too short to parse, then a good one.
    remainder = client._consume_buffer("$%0$%00,1,0,0,00,READY$rest")
    assert remainder == "rest"
    assert len(events) == 1
    assert events[0].name == "keypad_update"


async def test_a_command_sent_without_a_session_is_a_connection_error():
    client = EnvisalinkClient("127.0.0.1", 4025, "user", event_callback=lambda event: None)
    with pytest.raises(TPIConnectionError, match="not connected"):
        await client.keep_alive()


async def test_the_default_partition_command_reaches_the_panel():
    server = FakeEnvisalinkServer()
    await server.start()
    try:
        client = EnvisalinkClient(
            "127.0.0.1", server.port, "user", event_callback=lambda event: None
        )
        await client.connect()
        try:
            await client.change_default_partition(2)
            await asyncio.sleep(0.05)
            assert ("01", "2") in server.received
        finally:
            await client.disconnect()
    finally:
        await server.stop()


async def test_a_keypress_is_one_character_at_a_time():
    client = EnvisalinkClient("127.0.0.1", 4025, "user", event_callback=lambda event: None)
    with pytest.raises(ValueError, match="one character"):
        await client.send_keypress(1, "12")
