"""Shared test helpers: a minimal fake Envisalink TPI server."""
from __future__ import annotations

import asyncio

from custom_components.envisalink_field_programmer.client import compute_checksum


def frame(code: str, data: str = "") -> bytes:
    payload = f"{code}{data}"
    return f"{payload}{compute_checksum(payload)}\r\n".encode("ascii")


class FakeEnvisalinkServer:
    """A minimal fake EVL TPI server for one connection at a time."""

    def __init__(self, password: str = "user") -> None:
        self.password = password
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
        assert self._writer is not None
        self._writer.write(frame(code, data))
        await self._writer.drain()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._writer = writer
        writer.write(frame("505", "3"))
        await writer.drain()
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout=5)
        except (TimeoutError, asyncio.IncompleteReadError):
            return
        line = raw.decode("ascii").strip("\r\n")
        payload, _checksum = line[:-2], line[-2:]
        code, data = payload[:3], payload[3:]
        self.received.append((code, data))
        if code == "005" and data == self.password:
            writer.write(frame("505", "1"))
        else:
            writer.write(frame("505", "0"))
        await writer.drain()
        if code == "005" and data != self.password:
            writer.close()
            return
        try:
            while True:
                raw = await reader.readuntil(b"\r\n")
                line = raw.decode("ascii").strip("\r\n")
                payload, _checksum = line[:-2], line[-2:]
                self.received.append((payload[:3], payload[3:]))
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
