"""Shared test helpers: a minimal fake Envisalink TPI server.

Implements the protocol the hardware speaks (see client.py's module
docstring): a plain-text ``Login:``/``OK``/``FAILED`` handshake,
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
        # then back to "00") to simulate buffer overruns / rejections. A None
        # entry holds that acknowledgement back until release_held_acks().
        self.ack_commands = True
        self.scripted_responses: dict[str, list[str | None]] = {}
        self._held_acks: list[str] = []
        # Close the connection, unanswered, once the typed keys end with this:
        # the module dropping the session part-way through a sequence.
        self.drop_on: str | None = None
        # Stands in for the real module's single TPI session: while this is
        # above zero the server sends the login prompt, reads the password and
        # then closes without answering, which is exactly what the hardware
        # did on 2026-09-05 when a client connected 4 ms after another let go.
        self.drop_logins = 0
        # With this set the server behaves like the real module, which admits
        # one TPI client at a time: a connection arriving while another is
        # still open is dropped during login exactly as above.
        self.single_session = False
        # Stands in for the panel's Program Mode reports: once the typed keys
        # end with this entry it sends CID 627 (Program Mode Entry), and *99
        # typed while open sends 628. None keeps the panel silent, as one with
        # a wrong installer code, armed, or locked out with *98 would be.
        self.program_mode_entry: str | None = "4112800"
        self.report_exit = True
        # More reports, keyed by what the typed keys end with, sent in the
        # same write as the keypress's acknowledgement.
        self.extra_reports: dict[str, str] = {}
        self.in_program_mode = False
        self._typed = ""
        # How the panel answers ^01,<n> (change default partition): with a
        # keypad update for partition n if the panel has it. Whether a real
        # EnvisaLink does this is unverified; a test of a quiet module or a
        # panel with fewer partitions than the entry counts turns it off or
        # lowers panel_partitions.
        self.answer_partition_requests = True
        self.panel_partitions = 8
        self.partition_report = "1008,0,00,READY"
        self.partition_requests: list[int] = []
        self.default_partition = 1
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
            # transport has fully detached, not just the listening socket,
            # so a test that stops the server on a still-connected client --
            # which is how the reconnect tests simulate the module going
            # away -- would hang here. We only need the listening port freed
            # for the next test, which close() alone guarantees.

    async def enter_program_mode(self) -> None:
        """Open Program Mode as someone at the keypad would, and report it."""
        self.in_program_mode = True
        self._typed = ""
        await self.push("03", "1627" + "01" + "000")

    async def release_held_acks(self) -> None:
        """Send the acknowledgements held back by None responses, late."""
        assert self._writer is not None
        held, self._held_acks = self._held_acks, []
        self._writer.write("".join(held).encode("ascii"))
        await self._writer.drain()

    async def push(self, code: str, data: str = "") -> None:
        """Send a "%CODE,DATA$" frame to the connected client."""
        assert self._writer is not None
        self._writer.write(f"%{code},{data}$".encode("ascii"))
        await self._writer.drain()

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
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
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        busy: bool = False,
    ) -> None:
        writer.write(b"Login:\r\n")
        await writer.drain()
        try:
            raw = await asyncio.wait_for(reader.readuntil(b"\r\n"), timeout=5)
        except TimeoutError, asyncio.IncompleteReadError:
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
                    if parsed is None:
                        continue
                    if self.drop_on is not None and parsed[0] == "03":
                        typed = self._typed + parsed[1].split(",", 1)[-1]
                        if typed.endswith(self.drop_on):
                            self._typed = typed
                            writer.close()
                            return
                    # One write, so the client reads the acknowledgement and the
                    # panel's reports together, as one TCP segment can carry them.
                    out = ""
                    response: str | None = "00"
                    if self.ack_commands:
                        code, _ = parsed
                        response = self._next_response(code)
                        if response is None:
                            # Held back, but the panel still got the key.
                            self._held_acks.append(f"^{code},00$")
                            response = "00"
                        else:
                            out += f"^{code},{response}$"
                    # A refused command never reaches the panel.
                    if response == "00":
                        out += "".join(
                            f"%03,{r}$" for r in self._panel_reports(*parsed)
                        )
                        out += self._partition_answer(*parsed)
                    if out:
                        writer.write(out.encode("ascii"))
                        await writer.drain()
        except asyncio.IncompleteReadError, ConnectionResetError:
            pass

    def _panel_reports(self, code: str, data: str) -> list[str]:
        """The CID events the panel reports after this keypress."""
        if code != "03" or "," not in data:
            return []
        self._typed += data.split(",", 1)[1]
        reports = [
            r for end, r in self.extra_reports.items() if self._typed.endswith(end)
        ]
        # qualifier, CID event, partition 01, zone or user 000
        if not self.in_program_mode and self.program_mode_entry is not None:
            if self._typed.endswith(self.program_mode_entry):
                self.in_program_mode = True
                reports.insert(0, "1627" + "01" + "000")
        elif self.in_program_mode and self._typed.endswith("*99"):
            self.in_program_mode = False
            if self.report_exit:
                reports.append("1628" + "01" + "000")
        return reports

    def _partition_answer(self, code: str, data: str) -> str:
        """The keypad update the panel sends when the default partition changes."""
        if code != "01" or not data.isdigit():
            return ""
        partition = int(data)
        self.partition_requests.append(partition)
        self.default_partition = partition
        if not self.answer_partition_requests or partition > self.panel_partitions:
            return ""
        return f"%00,{partition:02d},{self.partition_report}$"

    def _next_response(self, code: str) -> str | None:
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
