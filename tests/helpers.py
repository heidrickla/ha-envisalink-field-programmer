"""Shared test helpers: a minimal fake Envisalink TPI server.

Implements the real protocol (see client.py's module docstring for the
correction history): a plain-text ``Login:``/``OK``/``FAILED`` handshake,
then ``%CODE,DATA$`` (server -> client) / ``^CODE,DATA$`` (client -> server)
framing with no checksum.
"""
from __future__ import annotations

import asyncio


class FakeEnvisalinkServer:
    """A minimal fake EVL TPI server for one connection at a time."""

    def __init__(self, password: str = "user") -> None:
        self.password = password
        # (code, data) pairs received from the client, code without its "^"
        # sentinel, e.g. ("03", "1,4") for a keypress of "4" to partition 1.
        self.received: list[tuple[str, str]] = []
        self._server: asyncio.AbstractServer | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.port: int = 0

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
        if self._server is not None:
            self._server.close()
            # Deliberately not awaiting wait_closed(): on Python 3.12+,
            # Server.wait_closed() blocks until every accepted connection's
            # transport has fully detached, not just the listening socket.
            # Our EnvisalinkClient.disconnect() cancels its read task and
            # closes its writer without awaiting the cancellation settling,
            # so that detach can lag well behind this call returning. We
            # only need the listening port freed for the next test, which
            # close() alone guarantees.

    async def push(self, code: str, data: str = "") -> None:
        """Send a "%CODE,DATA$" frame to the connected client."""
        assert self._writer is not None
        self._writer.write(f"%{code},{data}$".encode("ascii"))
        await self._writer.drain()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writer = writer
        writer.write(b"Login:\r\n")
        await writer.drain()
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout=5)
        except (TimeoutError, asyncio.IncompleteReadError):
            return
        password = raw.decode("ascii", errors="ignore").strip("\r\n")

        if password == self.password:
            writer.write(b"OK\r\n")
        else:
            writer.write(b"FAILED\r\n")
        await writer.drain()
        if password != self.password:
            writer.close()
            return

        buffer = ""
        try:
            while True:
                chunk = await reader.read(512)
                if not chunk:
                    break
                buffer += chunk.decode("ascii", errors="ignore")
                frames = buffer.split("$")
                buffer = frames.pop()
                for raw_frame in frames:
                    self._record_frame(raw_frame)
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass

    def _record_frame(self, raw_frame: str) -> None:
        frame = raw_frame
        for idx, char in enumerate(raw_frame):
            if char in "%^":
                frame = raw_frame[idx:]
                break
        if len(frame) >= 4 and frame[3] == ",":
            self.received.append((frame[1:3], frame[4:]))
