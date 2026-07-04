"""Asyncio client for the EnvisaLink Third Party Interface (TPI) protocol.

Implements the wire protocol described in the EnvisaLink TPI Programmer's
Document v1.08 (2017-02-10): hex-ASCII framing with a checksum, a
password-based login handshake, and a set of 3-digit command codes for
outbound (application -> EVL) and inbound (EVL -> application) traffic.

This module has no dependency on Home Assistant and can be unit tested with
plain asyncio streams (e.g. a loopback socket or ``asyncio.StreamReader``
fed by hand).
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from .const import COMMAND_NAMES, COMMAND_SCHEMA

_LOGGER = logging.getLogger(__name__)

FRAME_TERMINATOR = b"\r\n"
MAX_KEYSTROKES_PER_FRAME = 6


class TPIError(Exception):
    """Base error for TPI client failures."""


class TPIConnectionError(TPIError):
    """Raised when the TCP connection or login handshake fails."""


class TPIAuthError(TPIError):
    """Raised when the Envisalink rejects the configured password."""


class TPIProtocolError(TPIError):
    """Raised when a frame is malformed or fails its checksum."""


@dataclass
class TPIEvent:
    """A single parsed frame received from the Envisalink."""

    code: str
    name: str
    raw_data: str
    fields: dict[str, str] = field(default_factory=dict)

    @property
    def partition(self) -> int | None:
        value = self.fields.get("partition")
        return int(value) if value else None

    @property
    def zone(self) -> int | None:
        value = self.fields.get("zone")
        return int(value) if value else None


def compute_checksum(payload: str) -> str:
    """Sum the ASCII codes of every character in ``payload``, mod 256, as hex."""
    total = sum(ord(c) for c in payload) & 0xFF
    return f"{total:02X}"


def parse_frame(line: str) -> tuple[str, str]:
    """Split a raw (checksum-verified) line into (command_code, data)."""
    if len(line) < 5:
        raise TPIProtocolError(f"frame too short: {line!r}")
    payload, checksum = line[:-2], line[-2:]
    expected = compute_checksum(payload)
    if checksum.upper() != expected.upper():
        raise TPIProtocolError(
            f"checksum mismatch for {line!r}: got {checksum}, expected {expected}"
        )
    return payload[:3], payload[3:]


def build_event(code: str, data: str) -> TPIEvent:
    """Turn a (command_code, data) pair into a structured TPIEvent."""
    name = COMMAND_NAMES.get(code, "unknown")
    schema = COMMAND_SCHEMA.get(code)
    fields: dict[str, str] = {}
    if schema is not None:
        offset = 0
        for field_name, length in schema:
            fields[field_name] = data[offset : offset + length]
            offset += length
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
        open_connection: Callable[[str, int], Awaitable[tuple]] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._password = password
        self._event_callback = event_callback
        self._disconnect_callback = disconnect_callback
        self._login_timeout = login_timeout
        self._open_connection = open_connection or asyncio.open_connection
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._read_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def connect(self) -> None:
        """Open the TCP connection and complete the login handshake."""
        reader, writer = await self._open_connection(self._host, self._port)
        try:
            line = await asyncio.wait_for(
                self._read_line(reader), timeout=self._login_timeout
            )
            if line is None:
                raise TPIConnectionError("connection closed before login prompt")
            code, data = parse_frame(line)
            if code != "505" or data != "3":
                raise TPIConnectionError(
                    f"expected password request (505 3), got {code} {data!r}"
                )

            await self._write_frame(writer, "005", self._password)

            line = await asyncio.wait_for(
                self._read_line(reader), timeout=self._login_timeout
            )
            if line is None:
                raise TPIConnectionError("connection closed during login")
            code, data = parse_frame(line)
            if code != "505":
                raise TPIConnectionError(
                    f"expected login result (505), got {code} {data!r}"
                )
            if data == "0":
                raise TPIAuthError("Envisalink rejected the configured password")
            if data == "2":
                raise TPIConnectionError("login timed out waiting for password")
            if data != "1":
                raise TPIConnectionError(f"unexpected login status {data!r}")
        except Exception:
            writer.close()
            raise

        self._reader = reader
        self._writer = writer
        self._read_task = asyncio.ensure_future(self._read_loop())

    async def disconnect(self) -> None:
        if self._read_task is not None:
            self._read_task.cancel()
            self._read_task = None
        if self._writer is not None:
            self._writer.close()
            self._writer = None
        self._reader = None

    async def _read_loop(self) -> None:
        error: Exception | None = None
        try:
            while True:
                assert self._reader is not None
                line = await self._read_line(self._reader)
                if line is None:
                    break
                try:
                    code, data = parse_frame(line)
                except TPIProtocolError:
                    _LOGGER.warning("Dropping malformed TPI frame: %r", line)
                    continue
                event = build_event(code, data)
                self._event_callback(event)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # noqa: BLE001 - surface any failure to caller
            error = err
            _LOGGER.debug("TPI read loop ended with error", exc_info=err)
        finally:
            if self._disconnect_callback is not None:
                self._disconnect_callback(error)

    @staticmethod
    async def _read_line(reader: asyncio.StreamReader) -> str | None:
        try:
            raw = await reader.readuntil(FRAME_TERMINATOR)
        except asyncio.IncompleteReadError as err:
            if not err.partial:
                return None
            raw = err.partial
        except asyncio.LimitOverrunError as err:
            raise TPIProtocolError("frame exceeded buffer limit") from err
        if not raw:
            return None
        return raw.decode("ascii", errors="ignore").strip("\r\n")

    @staticmethod
    async def _write_frame(writer: asyncio.StreamWriter, code: str, data: str = "") -> None:
        payload = f"{code}{data}"
        checksum = compute_checksum(payload)
        writer.write(f"{payload}{checksum}\r\n".encode("ascii"))
        await writer.drain()

    async def _send(self, code: str, data: str = "") -> None:
        if self._writer is None:
            raise TPIConnectionError("not connected")
        async with self._write_lock:
            await self._write_frame(self._writer, code, data)

    # -- Outbound commands ------------------------------------------------

    async def poll(self) -> None:
        await self._send("000")

    async def status_report(self) -> None:
        await self._send("001")

    async def arm_away(self, partition: int) -> None:
        await self._send("030", str(partition))

    async def arm_stay(self, partition: int) -> None:
        await self._send("031", str(partition))

    async def arm_zero_entry(self, partition: int) -> None:
        await self._send("032", str(partition))

    async def arm_with_code(self, partition: int, code: str) -> None:
        await self._send("033", f"{partition}{code.ljust(6, '0')}")

    async def disarm(self, partition: int, code: str) -> None:
        await self._send("040", f"{partition}{code.ljust(6, '0')}")

    async def command_output(self, partition: int, output: int) -> None:
        await self._send("020", f"{partition}{output}")

    async def code_send(self, code: str) -> None:
        await self._send("200", code)

    async def keep_alive(self, partition: int) -> None:
        await self._send("074", str(partition))

    async def enter_user_code_programming(self, partition: int) -> None:
        await self._send("072", str(partition))

    async def enter_user_programming(self, partition: int) -> None:
        await self._send("073", str(partition))

    async def send_keystrokes(self, partition: int, keys: str) -> None:
        """Send an arbitrary keystroke string, chunked into <=6-key frames.

        WARNING: This is the mechanism the panel uses for everything from
        zone bypass to full installer field programming. There is no
        error-checking of panel state on the wire -- see
        ``programming.py`` for the safety guardrails built on top of this.
        """
        if not keys:
            return
        for start in range(0, len(keys), MAX_KEYSTROKES_PER_FRAME):
            chunk = keys[start : start + MAX_KEYSTROKES_PER_FRAME]
            await self._send("071", f"{partition}{chunk}")
