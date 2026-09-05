"""What the login handshake is allowed to write to the log.

The debug line exists because a password the module rejected could not be
told apart from a password the browser mangled on the way in: the length and
shape settle that. The password itself must never be written down, so the
absence is asserted here rather than left to review.
"""

from __future__ import annotations

import logging

import pytest

from tests import pure
from tests.helpers import FakeEnvisalinkServer

client_module = pure.load("client")
EnvisalinkClient = client_module.EnvisalinkClient
TPIAuthError = client_module.TPIAuthError

SECRET = "s3cr3t-pw"
LOGGER_NAME = client_module._LOGGER.name


@pytest.fixture
async def fake_server():
    server = FakeEnvisalinkServer(password=SECRET)
    await server.start()
    yield server
    await server.stop()


def _assert_secret_absent(caplog: pytest.LogCaptureFixture) -> None:
    """No record may carry the password, formatted or as an argument.

    Both halves are checked because a log record keeps its arguments
    unformatted until something asks for the message: a password passed as an
    argument would not appear in ``getMessage()`` here and would still be
    written to the log file.
    """
    for record in caplog.records:
        assert SECRET not in record.getMessage()
        assert SECRET not in repr(record.args)
        assert SECRET not in str(record.msg)


async def test_the_handshake_log_describes_the_password_without_recording_it(fake_server, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        client = EnvisalinkClient(
            "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
        )
        await client.connect()
        await client.disconnect()

    # Positive control on the same axis: the log really did describe this
    # login, so the absence below is not just an absence of logging.
    messages = [record.getMessage() for record in caplog.records]
    assert any(f"sending a {len(SECRET)}-character password" in message for message in messages)
    assert any("module answered 'OK'" in message for message in messages)
    _assert_secret_absent(caplog)


async def test_a_rejected_password_is_not_written_to_the_log(fake_server, caplog):
    with caplog.at_level(logging.DEBUG, logger=LOGGER_NAME):
        client = EnvisalinkClient(
            "127.0.0.1", fake_server.port, SECRET, event_callback=lambda _event: None
        )
        fake_server.password = "something else"
        with pytest.raises(TPIAuthError):
            await client.connect()

    assert any("module answered 'FAILED'" in record.getMessage() for record in caplog.records)
    _assert_secret_absent(caplog)
