"""Asyncio client for the real EnvisaLink TPI protocol.

CORRECTNESS NOTE: an earlier version of this module implemented a
hex-ASCII, checksum-framed protocol taken from the "EnvisaLink TPI
Programmer's Document v1.08" PDF. That does not match what a real EVL-4 +
VISTA-21iP actually speaks -- confirmed directly against live hardware
(see DEVELOPMENT.md for how this was discovered). This rewrite implements
the protocol that hardware actually uses, cross-checked against the
actively maintained `pyenvisalink` library:

  * Login is plain text: the EVL sends the literal line ``Login:``, the
    client replies with just the password, and the EVL replies ``OK``,
    ``FAILED``, or ``Timed Out!`` -- all newline-terminated, no framing.
  * Every message after that is ``%CODE,DATA$`` (EVL -> client) or
    ``^CODE,DATA$`` (client -> EVL), terminated by ``$``. There is no
    checksum.
  * Keystrokes go one character at a time via ``^03,<partition>,<char>$``.
  * The EVL processes exactly ONE command at a time: every command is
    answered with a ``^CODE,<response>$`` acknowledgement, and a command
    sent while the previous one is still being processed is rejected with
    response code 01 ("Receive Buffer Overrun"). ``_send()`` therefore
    serializes commands and waits for each ack (retrying on overrun),
    mirroring `pyenvisalink`'s command queue -- without this, only the
    first keystroke of a multi-key sequence (an arm/disarm code, a bypass)
    ever reaches the panel.

This module has no dependency on Home Assistant and can be unit tested with
plain asyncio streams (e.g. a loopback socket or ``asyncio.StreamReader``
fed by hand).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .const import (
    CMD_CHANGE_DEFAULT_PARTITION,
    CMD_DUMP_ZONE_TIMERS,
    CMD_KEYPRESS,
    CMD_POLL,
    COMMAND_ACK_TIMEOUT,
    COMMAND_NAMES,
    COMMAND_RETRY_ATTEMPTS,
    COMMAND_RETRY_DELAY,
    EVT_KEYPAD_UPDATE,
    EVT_REALTIME_CID_EVENT,
    FRAME_SENTINELS,
    FRAME_TERMINATOR,
    LOGIN_FAILURE,
    LOGIN_PROMPT,
    LOGIN_SUCCESS,
    LOGIN_TIMEOUT_MESSAGE,
    RESPONSE_ACCEPTED,
    RESPONSE_BUFFER_OVERRUN,
    TPI_RESPONSE_CODES,
)

_LOGGER = logging.getLogger(__name__)

LOGIN_LINE_TERMINATOR = b"\r\n"


class TPIError(Exception):
    """Base error for TPI client failures."""


class TPIConnectionError(TPIError):
    """Raised when the TCP connection or login handshake fails."""


class TPIAuthError(TPIError):
    """Raised when the Envisalink rejects the configured password."""


class TPIProtocolError(TPIError):
    """Raised when a frame is malformed."""


class TPICommandError(TPIError):
    """Raised when the EVL rejects a command or never acknowledges it."""


@dataclass
class TPIEvent:
    """A single parsed frame received from the Envisalink."""

    code: str
    name: str
    raw_data: str
    fields: dict[str, str | int] = field(default_factory=dict)


def strip_leading_garbage(frame: str) -> str:
    """Drop bytes preceding the frame's ``%``/``^`` sentinel.

    The Honeywell keybus can occasionally have bus corruption that leaves
    stray characters ahead of an otherwise-valid frame; the sentinel search
    lets us recover the frame anyway.
    """
    for idx, char in enumerate(frame):
        if char in FRAME_SENTINELS:
            return frame[idx:]
    return frame


def parse_frame(frame: str) -> tuple[str, str]:
    """Split a de-sentineled chunk like ``%00,1,...`` into (code, data)."""
    frame = strip_leading_garbage(frame)
    if len(frame) < 4 or frame[3] != ",":
        raise TPIProtocolError(f"malformed frame (expected %xx,... or ^xx,...): {frame!r}")
    return frame[:3], frame[4:]


def build_event(code: str, data: str) -> TPIEvent:
    """Turn a (code, data) pair into a structured TPIEvent.

    Only does generic wire-level tokenizing here (splitting comma-separated
    fields, slicing fixed-width CID sub-fields); deciding what those values
    *mean* for panel/zone state lives in state_machine.py.
    """
    name = COMMAND_NAMES.get(code, "unknown")
    fields: dict[str, str | int] = {}

    if code == EVT_KEYPAD_UPDATE:
        # "<partition>,<icon_led_hex>,<zone_or_beep_field>,<beep_hex>,<alpha>"
        # Alpha text may itself contain commas, so only split the first 4.
        parts = data.split(",", 4)
        if len(parts) == 5:
            fields["partition"] = parts[0]
            fields["icon_led_hex"] = parts[1]
            fields["zone_or_beep_field"] = parts[2]
            fields["beep_hex"] = parts[3]
            fields["alpha"] = parts[4]
    elif code == EVT_REALTIME_CID_EVENT:
        # Fixed-width: 1-digit qualifier, 3-digit CID event, 2-digit
        # partition, 3-digit zone-or-user.
        if len(data) >= 9:
            fields["qualifier"] = data[0]
            fields["cid_event"] = data[1:4]
            fields["partition"] = data[4:6]
            fields["zone_or_user"] = data[6:9]
    elif code.startswith("^") and len(data) >= 2:
        fields["response_code"] = data[:2]
    else:
        fields["raw"] = data

    return TPIEvent(code=code, name=name, raw_data=data, fields=fields)


EventCallback = Callable[[TPIEvent], None]
DisconnectCallback = Callable[[Exception | None], None]


class EnvisalinkClient:
    """Maintains a single TCP session with an Envisalink EVL-3/EVL-4."""

    def __init__(
        self,
        host: str,
        port: int,
        password: str,
        *,
        event_callback: EventCallback,
        disconnect_callback: DisconnectCallback | None = None,
        login_timeout: float = 10,
        ack_timeout: float = COMMAND_ACK_TIMEOUT,
        open_connection: (
            Callable[[str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]]
            | None
        ) = None,
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._event_callback = event_callback
        self._disconnect_callback = disconnect_callback
        self._login_timeout = login_timeout
        self._ack_timeout = ack_timeout
        self._open_connection = open_connection or asyncio.open_connection
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task[None] | None = None
        # Serializes whole command round-trips (write + wait for ack), not
        # just the writes -- the EVL only processes one command at a time.
        self._command_lock = asyncio.Lock()
        self._pending_ack: asyncio.Future[str] | None = None
        self._pending_ack_code = ""
        self._buffer = ""

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the TCP connection and complete the plain-text login handshake."""
        reader, writer = await self._open_connection(self._host, self._port)
        try:
            prompt = await asyncio.wait_for(
                self._read_login_line(reader), timeout=self._login_timeout
            )
            if prompt is None:
                raise TPIConnectionError("connection closed before login prompt")
            if prompt != LOGIN_PROMPT:
                raise TPIConnectionError(f"expected {LOGIN_PROMPT!r} login prompt, got {prompt!r}")

            # The password itself is never logged; its length and shape are
            # enough to tell a mangled value from a rejected one.
            _LOGGER.debug(
                "TPI login to %s:%s: got %r, sending a %d-character password (ascii=%s, stripped=%d)",
                self._host,
                self._port,
                prompt,
                len(self._password),
                self._password.isascii(),
                len(self._password.strip()),
            )
            writer.write(f"{self._password}\r\n".encode("ascii"))
            await writer.drain()

            result = await asyncio.wait_for(
                self._read_login_line(reader), timeout=self._login_timeout
            )
            _LOGGER.debug("TPI login to %s:%s: module answered %r", self._host, self._port, result)
            if result is None:
                raise TPIConnectionError("connection closed during login")
            if result == LOGIN_FAILURE:
                raise TPIAuthError("Envisalink rejected the configured password")
            if result == LOGIN_TIMEOUT_MESSAGE:
                raise TPIConnectionError("login timed out waiting for password")
            if result != LOGIN_SUCCESS:
                raise TPIConnectionError(f"unexpected login result {result!r}")
        except Exception:
            writer.close()
            raise

        self._reader = reader
        self._writer = writer
        self._buffer = ""
        self._read_task = asyncio.ensure_future(self._read_loop())

    async def disconnect(self) -> None:
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        self._reader = None
        self._abort_pending_ack("disconnected while awaiting command acknowledgement")

    def _abort_pending_ack(self, reason: str) -> None:
        """Fail a command waiting on its ack so it doesn't hang to timeout."""
        if self._pending_ack is not None and not self._pending_ack.done():
            self._pending_ack.set_exception(TPIConnectionError(reason))

    async def _read_loop(self) -> None:
        error: Exception | None = None
        try:
            assert self._reader is not None
            while True:
                chunk = await self._reader.read(512)
                if not chunk:
                    break
                self._buffer += chunk.decode("ascii", errors="ignore")
                self._buffer = self._consume_buffer(self._buffer)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - surface any failure to caller
            error = err
            _LOGGER.debug("TPI read loop ended with error", exc_info=err)
        finally:
            self._abort_pending_ack("connection lost while awaiting command acknowledgement")
            if self._disconnect_callback is not None:
                self._disconnect_callback(error)

    def _consume_buffer(self, buffer: str) -> str:
        """Split buffered bytes on ``$`` and dispatch each complete frame."""
        frames = buffer.split(FRAME_TERMINATOR)
        remainder = frames.pop()
        for frame in frames:
            frame = strip_leading_garbage(frame)
            if not frame:
                continue
            try:
                code, data = parse_frame(frame)
            except TPIProtocolError:
                _LOGGER.warning("Dropping malformed TPI frame: %r", frame)
                continue
            event = build_event(code, data)
            if (
                self._pending_ack is not None
                and not self._pending_ack.done()
                and event.code == self._pending_ack_code
            ):
                self._pending_ack.set_result(str(event.fields.get("response_code", event.raw_data)))
            self._event_callback(event)
        return remainder

    @staticmethod
    async def _read_login_line(reader: asyncio.StreamReader) -> str | None:
        try:
            raw = await reader.readuntil(LOGIN_LINE_TERMINATOR)
        except asyncio.IncompleteReadError as err:
            if not err.partial:
                return None
            raw = err.partial
        except asyncio.LimitOverrunError as err:
            raise TPIProtocolError("login line exceeded buffer limit") from err
        if not raw:
            return None
        return raw.decode("ascii", errors="ignore").strip("\r\n")

    async def _send(self, code: str, data: str = "") -> None:
        """Send one command frame and wait for the EVL's acknowledgement.

        The EVL processes exactly one command at a time and answers every
        command with ``^<code>,<response>$``; a command sent while the
        previous one is still in flight is rejected with response 01
        ("Receive Buffer Overrun"). So the full round-trip is serialized
        under the command lock -- write, await ack, retry on overrun --
        matching the reference `pyenvisalink` command queue. The trailing
        CRLF after the ``$`` terminator also matches that reference
        implementation.
        """
        payload = f"^{code},{data}$\r\n".encode("ascii")
        async with self._command_lock:
            for attempt in range(COMMAND_RETRY_ATTEMPTS + 1):
                if self._writer is None:
                    raise TPIConnectionError("not connected")
                future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                self._pending_ack_code = f"^{code}"
                self._pending_ack = future
                try:
                    self._writer.write(payload)
                    await self._writer.drain()
                    try:
                        response = await asyncio.wait_for(future, self._ack_timeout)
                    except TimeoutError as err:
                        raise TPICommandError(
                            f"no acknowledgement for command ^{code} within {self._ack_timeout}s"
                        ) from err
                finally:
                    self._pending_ack = None
                    self._pending_ack_code = ""
                if response == RESPONSE_ACCEPTED:
                    return
                if response == RESPONSE_BUFFER_OVERRUN and attempt < COMMAND_RETRY_ATTEMPTS:
                    # EVL still busy with the previous command (e.g. still
                    # clocking a keypress onto the keybus) -- back off and retry.
                    await asyncio.sleep(COMMAND_RETRY_DELAY * (2**attempt))
                    continue
                meaning = TPI_RESPONSE_CODES.get(response, "unrecognized response code")
                raise TPICommandError(
                    f"EVL rejected command ^{code}: response {response} ({meaning})"
                )

    # -- Outbound commands ------------------------------------------------

    async def keep_alive(self) -> None:
        """Reset the Envisalink's watchdog timer (also used as a liveness poll)."""
        await self._send(CMD_POLL)

    async def change_default_partition(self, partition: int) -> None:
        await self._send(CMD_CHANGE_DEFAULT_PARTITION, str(partition))

    async def dump_zone_timers(self) -> None:
        """Ask the panel for the 256-char zone timer dump (``%FF`` reply)."""
        await self._send(CMD_DUMP_ZONE_TIMERS)

    async def send_keypress(self, partition: int, key: str) -> None:
        if len(key) != 1:
            raise ValueError("send_keypress sends exactly one character at a time")
        await self._send(CMD_KEYPRESS, f"{partition},{key}")

    async def send_keystrokes(self, partition: int, keys: str) -> None:
        """Send an arbitrary keystroke string, one character per frame.

        WARNING: This is the mechanism the panel uses for everything from
        zone bypass and arming to full installer field programming. There
        is no error-checking of panel state on the wire -- see
        ``programming.py`` for the safety guardrails built on top of this.
        """
        for key in keys:
            await self.send_keypress(partition, key)
