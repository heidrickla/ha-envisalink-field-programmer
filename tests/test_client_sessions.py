"""The single-session rules: closing properly, and the retry that follows.

The Envisalink admits one TPI client at a time and only frees that slot when
it has seen the previous connection close. Two things follow, and both are
checked here: a disconnect waits for the close instead of merely asking for
it, and a connect the module drops part-way through login is tried once more
rather than failing outright.
"""

from __future__ import annotations

import asyncio

import pytest

from tests import pure
from tests.helpers import FakeEnvisalinkServer

client_module = pure.load("client")
EnvisalinkClient = client_module.EnvisalinkClient
TPIAuthError = client_module.TPIAuthError
TPIConnectionError = client_module.TPIConnectionError

SECRET = "s3cr3t-pw"


@pytest.fixture
async def fake_server():
    server = FakeEnvisalinkServer(password=SECRET)
    await server.start()
    yield server
    await server.stop()


async def test_disconnect_waits_for_the_close_instead_of_only_asking_for_it():
    """The module frees its session on the close, so the close is awaited."""

    calls: list[str] = []

    class _Reader:
        def __init__(self) -> None:
            self._lines = [b"Login:\r\n", b"OK\r\n"]

        async def readuntil(self, separator: bytes) -> bytes:
            return self._lines.pop(0)

        async def read(self, count: int) -> bytes:
            await asyncio.sleep(3600)
            return b""

    class _Writer:
        def write(self, data: bytes) -> None:
            return None

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            calls.append("close")

        async def wait_closed(self) -> None:
            calls.append("wait_closed")

        def is_closing(self) -> bool:
            return "close" in calls

    async def _open(host: str, port: int):
        return _Reader(), _Writer()

    client = EnvisalinkClient(
        "127.0.0.1", 4025, SECRET, event_callback=lambda _event: None, open_connection=_open
    )
    await client.connect()
    await client.disconnect()
    assert calls == ["close", "wait_closed"]
    assert not client.connected


async def test_a_failed_login_also_waits_for_its_close():
    """A probe that fails must still leave the module's session free."""

    calls: list[str] = []

    class _Reader:
        async def readuntil(self, separator: bytes) -> bytes:
            return b"Login:\r\n"

        async def read(self, count: int) -> bytes:
            return b""

    class _Writer:
        def write(self, data: bytes) -> None:
            raise OSError("the socket went away mid-login")

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            calls.append("close")

        async def wait_closed(self) -> None:
            calls.append("wait_closed")

        def is_closing(self) -> bool:
            return "close" in calls

    async def _open(host: str, port: int):
        return _Reader(), _Writer()

    client = EnvisalinkClient(
        "127.0.0.1", 4025, SECRET, event_callback=lambda _event: None, open_connection=_open
    )
    with pytest.raises(OSError):
        await client.connect()
    assert calls == ["close", "wait_closed"]


async def test_a_login_the_module_drops_is_tried_once_more(fake_server):
    # What the hardware did on 2026-09-05: the module had not yet noticed its
    # one session was free, so it read the password and closed without an
    # answer. The connection that follows the retry delay succeeds.
    fake_server.drop_logins = 1
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
    )
    await client.connect_with_retry(0.01)
    try:
        assert client.connected
        assert fake_server.connections == 2
    finally:
        await client.disconnect()


async def test_a_single_connect_still_fails_on_the_dropped_login(fake_server):
    # The positive control for the test above: without the retry this is a
    # failed setup, which is what Home Assistant was seeing.
    fake_server.drop_logins = 1
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
    )
    with pytest.raises(TPIConnectionError, match="during login"):
        await client.connect()
    assert fake_server.connections == 1


async def test_the_retry_gives_up_when_the_module_keeps_dropping(fake_server):
    fake_server.drop_logins = 2
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
    )
    with pytest.raises(TPIConnectionError, match="during login"):
        await client.connect_with_retry(0.01)
    assert fake_server.connections == 2


async def test_the_next_client_gets_in_as_soon_as_the_last_one_has_disconnected(fake_server):
    # The whole reason disconnect() waits: with the server admitting one
    # client at a time, the second connect is dropped while the first holds
    # the session and succeeds the moment the first has let go.
    fake_server.single_session = True
    first = EnvisalinkClient(
        "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
    )
    second = EnvisalinkClient(
        "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
    )
    await first.connect()
    try:
        with pytest.raises(TPIConnectionError, match="during login"):
            await second.connect()
    finally:
        await first.disconnect()
    await second.connect()
    try:
        assert second.connected
    finally:
        await second.disconnect()


async def test_the_retry_does_not_re_send_a_rejected_password(fake_server):
    # A wrong password is an answer, not a race: retrying it would only delay
    # the reauthentication flow.
    client = EnvisalinkClient(
        "127.0.0.1", fake_server.port, "wrong", event_callback=lambda _event: None
    )
    with pytest.raises(TPIAuthError):
        await client.connect_with_retry(0.01)
    assert fake_server.connections == 1
