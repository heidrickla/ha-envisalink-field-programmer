"""Asyncio client for the EnvisaLink TPI protocol.

The wire format below is what an EVL-4 and a VISTA-21iP speak, read off live
hardware and cross-checked against the `pyenvisalink` library. The
"EnvisaLink TPI Programmer's Document v1.08" PDF describes a different
variant of TPI, hex-ASCII and checksum-framed with 3-digit numeric command
codes, which this hardware does not answer.

  * Login is plain text: the EVL sends the literal line ``Login:``, the
    client replies with just the password, and the EVL replies ``OK``,
    ``FAILED``, or ``Timed Out!`` -- all newline-terminated, no framing.
  * Every message after that is ``%CODE,DATA$`` (EVL -> client) or
    ``^CODE,DATA$`` (client -> EVL), terminated by ``$``. There is no
    checksum.
  * Keystrokes go one character at a time via ``^03,<partition>,<char>$``.
  * The EVL processes exactly one command at a time: every command is
    answered with a ``^CODE,<response>$`` acknowledgement, and a command
    sent while the previous one is still being processed is rejected with
    response code 01 ("Receive Buffer Overrun"). ``_send()`` therefore
    serializes commands and waits for each ack, retrying on overrun.
    Without that, only the first keystroke of a multi-key sequence reaches
    the panel: an arm or disarm code, or a bypass.

This module has no dependency on Home Assistant and can be unit tested with
plain asyncio streams, such as a loopback socket or an
``asyncio.StreamReader`` fed by hand.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from .const import (
    CLOSE_TIMEOUT,
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


class TPISessionBusyError(TPIConnectionError):
    """Raised when the module prompts for the login and then hangs up unanswered.

    Measured 2026-09-05: this is how the module drops a client while it counts
    another connection against its one TPI session.
    """


class TPIAuthError(TPIError):
    """Raised when the Envisalink rejects the configured password."""


class TPIProtocolError(TPIError):
    """Raised when a frame is malformed."""


class TPICommandError(TPIError):
    """Raised when the EVL rejects a command or never acknowledges it."""


class TPICommandRefused(TPICommandError):
    """The EVL answered with a refusal, so the command never reached the panel."""


class TPINotSent(TPIConnectionError):
    """The command was never written: the session was down before the write."""


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
        raise TPIProtocolError(
            f"malformed frame (expected %xx,... or ^xx,...): {frame!r}"
        )
    return frame[:3], frame[4:]


def build_event(code: str, data: str) -> TPIEvent:
    """Turn a (code, data) pair into a structured TPIEvent.

    Only does generic wire-level tokenizing here (splitting comma-separated
    fields, slicing fixed-width CID sub-fields); deciding what those values
    mean for panel/zone state lives in state_machine.py.
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


def _retrieve_result(future: asyncio.Future[str]) -> None:
    """Mark an owed ack's outcome as seen; nobody may be left awaiting it."""
    if not future.cancelled():
        future.exception()


class KeyTyper(Protocol):
    """Types keys on a partition; ``guard`` runs before each key's write."""

    def __call__(
        self, partition: int, keys: str, guard: Callable[[], None] | None = None
    ) -> Awaitable[None]: ...


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
            Callable[
                [str, int], Awaitable[tuple[asyncio.StreamReader, asyncio.StreamWriter]]
            ]
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
        # Serializes whole keystroke sequences. A sequence that needs the
        # keypad to itself (Program Mode, from the entry to *99) holds it
        # through keypad(); every other sender waits for it.
        self._keypad_lock = asyncio.Lock()
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
                raise TPIConnectionError(
                    f"expected {LOGIN_PROMPT!r} login prompt, got {prompt!r}"
                )

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
            _LOGGER.debug(
                "TPI login to %s:%s: module answered %r", self._host, self._port, result
            )
            if result is None:
                raise TPISessionBusyError("connection closed during login")
            if result == LOGIN_FAILURE:
                raise TPIAuthError("Envisalink rejected the configured password")
            if result == LOGIN_TIMEOUT_MESSAGE:
                raise TPIConnectionError("login timed out waiting for password")
            if result != LOGIN_SUCCESS:
                raise TPIConnectionError(f"unexpected login result {result!r}")
        except BaseException:
            # BaseException, not Exception, so a cancellation counts too. The
            # socket exists here but the client does not own it yet, so a
            # connect cancelled mid-login -- the reconfigure flow releasing
            # the session out from under a reconnect -- would otherwise leave
            # it to the garbage collector, and the module would go on
            # thinking its one TPI slot was taken. _close_writer() closes
            # before it awaits anything, so the close lands even when the
            # wait is cancelled immediately.
            with contextlib.suppress(asyncio.CancelledError):
                await self._close_writer(writer)
            raise

        # An ack owed on the last session never comes on this one.
        self._abort_pending_ack("the session ended before the acknowledgement")
        self._pending_ack = None
        self._pending_ack_code = ""
        self._reader = reader
        self._writer = writer
        self._buffer = ""
        self._read_task = asyncio.ensure_future(self._read_loop())

    async def connect_with_retry(self, delay: float) -> None:
        """Connect, and try once more after ``delay`` if the module drops it.

        Measured against the hardware on 2026-09-05: something else
        disconnected, this client connected 4 ms later, and the module dropped
        the new connection part-way through the login because it had not yet
        noticed its single TPI session was free. One retry after a beat turns
        that into a connection instead of a failed setup.

        A rejected password is not retried -- TPIAuthError is not a
        TPIConnectionError -- so a wrong password still goes straight to
        reauthentication.
        """
        try:
            await self.connect()
        except (TPIConnectionError, OSError) as err:
            _LOGGER.debug(
                "First connect to %s:%s failed (%s); retrying once in %ss",
                self._host,
                self._port,
                err,
                delay,
            )
            await asyncio.sleep(delay)
            await self.connect()

    async def disconnect(self) -> None:
        """Close the session and wait for the socket to actually be gone.

        The Envisalink admits one TPI client at a time and only frees that
        slot when it sees the connection close, so closing the writer is not
        enough on its own: a caller that opens the next session immediately
        would race the module and be dropped during login. Awaiting
        ``wait_closed`` here is what makes "disconnected" true rather than
        merely requested. The wait is bounded, because a module that never
        acknowledges the close must not hold up a Home Assistant shutdown.

        A command still waiting on its acknowledgement is failed first, before
        anything is awaited, so it is told this was deliberate rather than
        being beaten to it by the read loop's own "connection lost".

        The read task is awaited out too. Cancelling it is not enough: its
        last act is the disconnect callback, and a caller that reconnects
        straight away would otherwise get that callback after the new session
        was up, reported against a socket that no longer exists.
        """
        self._abort_pending_ack("disconnected while awaiting command acknowledgement")
        read_task = self._read_task
        self._read_task = None
        if read_task is not None:
            read_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await read_task
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            await self._close_writer(writer)

    @staticmethod
    async def _close_writer(writer: asyncio.StreamWriter) -> None:
        """Close a writer and wait, briefly, for the close to land."""
        writer.close()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(writer.wait_closed(), timeout=CLOSE_TIMEOUT)

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
            self._abort_pending_ack(
                "connection lost while awaiting command acknowledgement"
            )
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
                self._pending_ack.set_result(
                    str(event.fields.get("response_code", event.raw_data))
                )
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

    async def _send(
        self, code: str, data: str = "", guard: Callable[[], None] | None = None
    ) -> None:
        """Send one command frame and wait for the EVL's acknowledgement.

        The EVL processes exactly one command at a time and answers every
        command with ``^<code>,<response>$``; a command sent while the
        previous one is still in flight is rejected with response 01
        ("Receive Buffer Overrun"). So the full round-trip is serialized
        under the command lock -- write, await ack, retry on overrun --
        matching the reference `pyenvisalink` command queue. The trailing
        CRLF after the ``$`` terminator also matches that reference
        implementation. ``guard`` runs under the lock right before each write,
        with no await between, and raises to stop the command.
        """
        payload = f"^{code},{data}$\r\n".encode("ascii")
        async with self._command_lock:
            await self._settle_owed_ack()
            for attempt in range(COMMAND_RETRY_ATTEMPTS + 1):
                if self._writer is None:
                    raise TPINotSent("not connected")
                if guard is not None:
                    guard()
                future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
                self._pending_ack_code = f"^{code}"
                self._pending_ack = future
                try:
                    self._writer.write(payload)
                    await self._writer.drain()
                    # wait() never cancels the future, so a caller that stops
                    # waiting leaves the ack owed rather than free to answer
                    # the next command.
                    if not (await asyncio.wait({future}, timeout=self._ack_timeout))[0]:
                        raise TPICommandError(
                            f"no acknowledgement for command ^{code} within {self._ack_timeout}s"
                        )
                    response = future.result()
                finally:
                    if future.done():
                        self._pending_ack = None
                        self._pending_ack_code = ""
                    else:
                        future.add_done_callback(_retrieve_result)
                if response == RESPONSE_ACCEPTED:
                    return
                if (
                    response == RESPONSE_BUFFER_OVERRUN
                    and attempt < COMMAND_RETRY_ATTEMPTS
                ):
                    # EVL still busy with the previous command (e.g. still
                    # clocking a keypress onto the keybus) -- back off and retry.
                    await asyncio.sleep(COMMAND_RETRY_DELAY * (2**attempt))
                    continue
                meaning = TPI_RESPONSE_CODES.get(response, "unrecognized response code")
                raise TPICommandRefused(
                    f"EVL rejected command ^{code}: response {response} ({meaning})"
                )

    async def _settle_owed_ack(self) -> None:
        """Wait out the ack of a command whose caller stopped waiting for it.

        An ack names only its command code, so one still owed would be taken
        as the next command's own. One that never comes leaves every later ack
        unmatched, so the session is closed and the reconnect starts afresh.
        """
        owed = self._pending_ack
        if owed is not None and not owed.done():
            if not (await asyncio.wait({owed}, timeout=self._ack_timeout))[0]:
                await self.disconnect()
                raise TPINotSent(
                    "the Envisalink never acknowledged an earlier command; "
                    "the session was closed"
                )
        self._pending_ack = None
        self._pending_ack_code = ""

    # -- Outbound commands ------------------------------------------------

    async def keep_alive(self) -> None:
        """Reset the Envisalink's watchdog timer (also used as a liveness poll)."""
        await self._send(CMD_POLL)

    async def change_default_partition(self, partition: int) -> None:
        await self._send(CMD_CHANGE_DEFAULT_PARTITION, str(partition))

    async def dump_zone_timers(self) -> None:
        """Ask the panel for the 256-char zone timer dump (``%FF`` reply)."""
        await self._send(CMD_DUMP_ZONE_TIMERS)

    async def send_keypress(
        self, partition: int, key: str, guard: Callable[[], None] | None = None
    ) -> None:
        if len(key) != 1:
            raise ValueError("send_keypress sends exactly one character at a time")
        await self._send(CMD_KEYPRESS, f"{partition},{key}", guard)

    @contextlib.asynccontextmanager
    async def keypad(self) -> AsyncIterator[KeyTyper]:
        """Hold the keypad for one sequence; the yielded sender types into it.

        Only the coordinator's async_keypad takes this, after its checks.
        """
        async with self._keypad_lock:
            yield self._type_keys

    async def _type_keys(
        self, partition: int, keys: str, guard: Callable[[], None] | None = None
    ) -> None:
        for key in keys:
            await self.send_keypress(partition, key, guard)
