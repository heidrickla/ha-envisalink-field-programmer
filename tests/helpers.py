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
        # Like the real EVL, acknowledge every command with "^<code>,00$".
        # Tests can disable this to simulate an unresponsive EVL, or script
        # specific responses per command code (each entry consumed once,
        # then back to "00") to simulate buffer overruns / rejections.
        self.ack_commands = True
        self.scripted_responses: dict[str, list[str]] = {}
        # Stands in for the real module's single TPI session: while this is
        # above zero the server sends the login prompt, reads the password and
        # then closes without answering, which is exactly what the hardware
        # did on 2026-09-05 when a client connected 4 ms after another let go.
        self.drop_logins = 0
        # With this set the server behaves like the real module, which admits
        # one TPI client at a time: a connection arriving while another is
        # still open is dropped during login exactly as above.
        self.single_session = False
        # Connections accepted, connections still open, and connections whose
        # handler has finished, so a test can assert a disconnect landed.
        self.connections = 0
        self.open_connections = 0
        self.closed_connections = 0
        self._server: asyncio.AbstractServer | None = None
        self._writer: asyncio.StreamWriter | None = None
        self.port: int = 0

    async def start(self, port: int = 0) -> None:
        """Listen on a free loopback port, or on ``port`` to stand in for a restarted EVL."""
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", port)
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

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        # Counted before the handshake: the module's slot is taken by the
        # connection, not by the login that follows it.
        busy = self.single_session and self.open_connections > 0
        self.open_connections += 1
        try:
            await self._serve(reader, writer, busy=busy)
        finally:
            self.open_connections -= 1
            self.closed_connections += 1

    async def _serve(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, *, busy: bool = False
    ) -> None:
        writer.write(b"Login:\r\n")
        await writer.drain()
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout=5)
        except (TimeoutError, asyncio.IncompleteReadError):
            return
        password = raw.decode("ascii", errors="ignore").strip("\r\n")

        if busy or self.drop_logins > 0:
            # Either another client holds the single session, or the module
            # has not noticed the last one went: it answers nothing at all
            # and drops the connection.
            if not busy:
                self.drop_logins -= 1
            writer.close()
            return

        # Only a connection that gets this far owns the writer push() uses.
        self._writer = writer
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
                    parsed = self._record_frame(raw_frame)
                    if parsed is not None and self.ack_commands:
                        code, _ = parsed
                        writer.write(f"^{code},{self._next_response(code)}$".encode("ascii"))
                        await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass

    def _next_response(self, code: str) -> str:
        queue = self.scripted_responses.get(code)
        if queue:
            return queue.pop(0)
        return "00"

    def _record_frame(self, raw_frame: str) -> tuple[str, str] | None:
        frame = raw_frame
        for idx, char in enumerate(raw_frame):
            if char in "%^":
                frame = raw_frame[idx:]
                break
        if len(frame) >= 4 and frame[3] == ",":
            parsed = (frame[1:3], frame[4:])
            self.received.append(parsed)
            return parsed
        return None
