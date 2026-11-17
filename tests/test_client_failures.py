"""Every way the TPI session can go wrong before or after the handshake.

The login is plain text over a raw socket, so each failure is scripted by a
tiny server that answers with exactly the bytes being tested.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

import pytest

from tests import pure
from tests.helpers import FakeEnvisalinkServer

client_module = pure.load("client")
EnvisalinkClient = client_module.EnvisalinkClient
TPIAuthError = client_module.TPIAuthError
TPIConnectionError = client_module.TPIConnectionError
TPISessionBusyError = client_module.TPISessionBusyError
TPIProtocolError = client_module.TPIProtocolError
TPIError = client_module.TPIError
TPICommandError = client_module.TPICommandError

Handler = Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]]


class _ScriptedServer:
    """Answers one connection with whatever the handler writes."""

    def __init__(self, handler: Handler) -> None:
        self._handler = handler
        self._server: asyncio.AbstractServer | None = None
        self._connections: list[asyncio.Task] = []
        self.port = 0

    async def _serve(self, reader, writer) -> None:
        # asyncio gives every connection its own task. Closing the listening
        # socket does not touch those, so remember them for stop() to cancel:
        # a handler still sleeping out its script outlives the test otherwise.
        task = asyncio.current_task()
        if task is not None:
            self._connections.append(task)
        await self._handler(reader, writer)

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
        for task in self._connections:
            task.cancel()
        if self._connections:
            await asyncio.gather(*self._connections, return_exceptions=True)
        self._connections.clear()


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

    with pytest.raises(TPIConnectionError, match="before login prompt") as caught:
        await _connect_to(_handler)
    # No prompt means no Envisalink answered, so nothing says the session is held.
    assert not isinstance(caught.value, TPISessionBusyError)


async def test_something_that_is_not_an_envisalink_is_a_connection_error():
    async def _handler(reader, writer):
        writer.write(b"SSH-2.0-OpenSSH_9.6\r\n")
        await writer.drain()

    with pytest.raises(TPIConnectionError, match="login prompt"):
        await _connect_to(_handler)


async def test_a_socket_that_closes_after_the_prompt_is_a_held_session():
    # The module's way of turning away a client while another holds its one
    # TPI session. The prompt also arrives without its line ending, which the
    # reader recovers from the partial read.
    async def _handler(reader, writer):
        writer.write(b"Login:")
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    with pytest.raises(TPISessionBusyError, match="during login"):
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

        async def wait_closed(self) -> None:
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
    client = EnvisalinkClient(
        "127.0.0.1", 4025, "user", event_callback=lambda event: None
    )
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
    client = EnvisalinkClient(
        "127.0.0.1", 4025, "user", event_callback=lambda event: None
    )
    with pytest.raises(ValueError, match="one character"):
        await client.send_keypress(1, "12")


@pytest.mark.parametrize("abandon", ["timeout", "cancel"])
async def test_an_abandoned_command_s_ack_is_not_taken_by_the_next(abandon):
    # Acknowledgements carry no sequence number. A keypress given up before
    # its ack must not lend that ack to the next keypress, which would then
    # count as delivered while the module was still busy with the first.
    server = FakeEnvisalinkServer()
    await server.start()
    server.scripted_responses["03"] = [None, None]
    client = EnvisalinkClient(
        "127.0.0.1",
        server.port,
        "user",
        event_callback=lambda event: None,
        ack_timeout=0.3,
    )
    try:
        await client.connect()
        first = asyncio.ensure_future(client.send_keypress(1, "1"))
        if abandon == "timeout":
            with pytest.raises(TPICommandError):
                await first
        else:
            await asyncio.sleep(0.05)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        second = asyncio.ensure_future(client.send_keypress(1, "2"))
        await asyncio.sleep(0.05)
        # The first key's ack arrives late; the second key's ack is held.
        await server.release_held_acks()
        await asyncio.sleep(0.1)
        assert not (second.done() and second.exception() is None), (
            "the second key took the first key's acknowledgement"
        )
        second.cancel()
        with contextlib.suppress(asyncio.CancelledError, TPIError):
            await second
    finally:
        await client.disconnect()
        await server.stop()


async def test_an_ack_that_never_comes_ends_the_session():
    # Every later ack would be one behind, so the session is closed and the
    # next command fails instead of being matched to the wrong answer.
    server = FakeEnvisalinkServer()
    await server.start()
    server.scripted_responses["03"] = [None]
    lost: list[Exception | None] = []
    client = EnvisalinkClient(
        "127.0.0.1",
        server.port,
        "user",
        event_callback=lambda event: None,
        disconnect_callback=lost.append,
        ack_timeout=0.2,
    )
    try:
        await client.connect()
        with pytest.raises(TPICommandError):
            await client.send_keypress(1, "1")
        with pytest.raises(TPIConnectionError, match="never acknowledged"):
            await client.send_keypress(1, "2")
        assert not client.connected
        assert len(lost) == 1
        assert [d for c, d in server.received if c == "03"] == ["1,1"]
    finally:
        await client.disconnect()
        await server.stop()


async def test_an_ack_owed_on_a_lost_session_is_not_waited_for_on_the_next():
    # A command written after the module dropped the socket is never
    # answered; the session that replaces it owes nothing.
    server = FakeEnvisalinkServer()
    await server.start()
    lost: list[Exception | None] = []
    client = EnvisalinkClient(
        "127.0.0.1",
        server.port,
        "user",
        event_callback=lambda event: None,
        disconnect_callback=lost.append,
        ack_timeout=0.3,
    )
    try:
        await client.connect()
        assert server._writer is not None
        server._writer.close()
        for _ in range(100):
            if lost:
                break
            await asyncio.sleep(0.01)
        assert len(lost) == 1
        with pytest.raises((TPIError, OSError)):
            await client.send_keypress(1, "1")
        await client.connect()
        await asyncio.wait_for(client.keep_alive(), 0.2)
        assert client.connected
        assert server.connections == 2
    finally:
        await client.disconnect()
        await server.stop()
