"""Random interleavings of what the panel and the user can do around Program Mode.

Hypothesis generates sequences of panel reports (627, 628, armed and disarmed
partitions, tracked, untracked and garbled), acknowledgements held and
released late, writers cancelled while their ack is owed, dropped sessions,
reconnects, reloads, repairs, and everyday, guided and installer writers. They
run against the real coordinator and client over an in-memory session.

A reference model folds the same steps by the documented rules, without
reading the integration's state. Every keypress is checked at its write
against the model, and after every step the integration's Program Mode must
equal the model's.
"""

from __future__ import annotations

import asyncio
import contextvars
from dataclasses import dataclass, field
from typing import Any

from homeassistant.helpers import issue_registry as ir
from hypothesis import HealthCheck, example, given, settings
from hypothesis import strategies as st
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.envisalink_field_programmer import field_programming_services
from custom_components.envisalink_field_programmer.client import EnvisalinkClient
from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.coordinator import (
    VistaConsoleCoordinator,
)
from custom_components.envisalink_field_programmer.field_programming import (
    FunctionKeyAction,
    FunctionKeyLetter,
)
from custom_components.envisalink_field_programmer.models import ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import (
    ModeEvent,
    ModeState,
)
from custom_components.envisalink_field_programmer.programming import (
    async_send_guarded_keystrokes,
)

TRACKED = 2
INSTALLER_CODE = "4112"
ENTRY = "4112800"
# Enough loop turns for every task to reach its next real wait.
SETTLE_TURNS = 40

REPORTS = {
    "627": "%03,1627" + "01" + "000$",
    "628": "%03,1628" + "01" + "000$",
    "armed 1": "%00,1,000C,0,00,ARMED AWAY$",
    "armed 2": "%00,2,000C,0,00,ARMED AWAY$",
    "armed 3": "%00,3,000C,0,00,ARMED AWAY$",
    "armed x": "%00,x,000C,0,00,ARMED AWAY$",
    "disarmed 1": "%00,1,1008,0,00,READY$",
    "disarmed 2": "%00,2,1008,0,00,READY$",
}

STEPS = st.one_of(
    st.tuples(st.just("start"), st.sampled_from(["everyday", "guided", "installer"])),
    st.tuples(st.just("ack"), st.sampled_from(["00", "00", "01", "02"])),
    st.tuples(st.just("ack"), st.sampled_from(["00", "01", "02"])),
    st.tuples(st.just("ack"), st.just("00")),
    st.tuples(st.just("cancel"), st.integers(0, 3)),
    st.tuples(st.just("report"), st.sampled_from(sorted(REPORTS))),
    st.tuples(st.just("report"), st.sampled_from(["627", "628"])),
    st.tuples(st.just("drop"), st.just(0)),
    st.tuples(st.just("reconnect"), st.just(0)),
    st.tuples(st.just("reload"), st.just(0)),
    st.tuples(st.just("repair"), st.sampled_from(["current", "old"])),
)

_writer: contextvars.ContextVar[Writer | None] = contextvars.ContextVar(
    "writer", default=None
)


@dataclass
class Writer:
    use: str
    task: asyncio.Task[None] | None = None
    written: int = 0
    # The model's change count when this writer's own key raised the doubt,
    # and when the panel reported its entry open.
    raised_at: int | None = None
    opened_at: int | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()


@dataclass
class Model:
    """What the documented rules say Program Mode is, from the steps alone."""

    state: ProgramMode = ProgramMode.CLOSED
    changes: int = 0
    armed: dict[int, bool] = field(default_factory=dict)
    writers: list[Writer] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    panel_open: bool = False
    saw_627: bool = False
    entry_gates: int = 0
    keys_after_entry: int = 0
    refused_keys: int = 0
    repairs_tried: int = 0

    def set(self, state: ProgramMode) -> None:
        if state is not self.state:
            self.state = state
            self.changes += 1

    def holder_has_typed(self) -> bool:
        return any(
            w.running and w.use != "everyday" and w.written > 0 for w in self.writers
        )

    def report(self, name: str) -> None:
        if name == "627":
            before = self.changes
            self.state = ProgramMode.OPEN
            self.changes += 1
            self.panel_open = True
            self.saw_627 = True
            # A guided entry's own 627 is the one change after its doubt.
            for w in self.writers:
                if (
                    w.running
                    and w.use == "guided"
                    and w.written == len(ENTRY)
                    and w.raised_at == before
                    and self.changes == before + 1
                ):
                    w.opened_at = self.changes
        elif name == "628":
            self.state = ProgramMode.CLOSED
            self.changes += 1
            self.panel_open = False
            self.saw_627 = False
        else:
            kind, _, number = name.partition(" ")
            if not number.isdigit() or not 1 <= int(number) <= TRACKED:
                return
            self.armed[int(number)] = kind == "armed"
            if (
                kind == "armed"
                and self.state is ProgramMode.DOUBT
                and not self.saw_627
                and not self.holder_has_typed()
            ):
                self.set(ProgramMode.CLOSED)

    def session_ended(self) -> None:
        # A change either way: keys belong to the session their entry used.
        if self.state is ProgramMode.OPEN:
            self.set(ProgramMode.DOUBT)
        else:
            self.changes += 1

    def write(self, writer: Writer | None, key: str) -> None:
        """Check one keypress at the instant it is written, then fold it."""
        if writer is None:
            self.violations.append(f"key {key!r} written by no writer")
            return
        index = writer.written
        writer.written += 1
        where = f"{writer.use} key {index} ({key!r}) in {self.state.value}"
        if writer.use == "everyday":
            if self.panel_open or self.state is not ProgramMode.CLOSED:
                self.violations.append(where)
        elif writer.use == "installer":
            if self.state is ProgramMode.CLOSED:
                self.set(ProgramMode.DOUBT)
        elif index < len(ENTRY):
            self.entry_gates += 1
            if any(self.armed.values()):
                self.violations.append(where + " with a partition armed")
            if index == 0:
                if self.state is not ProgramMode.CLOSED:
                    self.violations.append(where)
                self.set(ProgramMode.DOUBT)
                writer.raised_at = self.changes
            elif (
                self.state is not ProgramMode.DOUBT or self.changes != writer.raised_at
            ):
                self.violations.append(where + " after the state changed")
        elif self.state is not ProgramMode.OPEN or self.changes != writer.opened_at:
            self.keys_after_entry += 1
            self.violations.append(where + " outside its own Program Mode")
        else:
            self.keys_after_entry += 1


class Session:
    """One in-memory TPI session, standing in for the socket."""

    def __init__(self, model: Model) -> None:
        self.reader = asyncio.StreamReader()
        self.reader.feed_data(b"Login:\r\n")
        self._model = model
        self._logged_in = False
        self.dropped = False
        self.unacked = 0
        self.key_writes = 0

    def write(self, data: bytes) -> None:
        if not self._logged_in:
            self._logged_in = True
            self.reader.feed_data(b"OK\r\n")
            return
        # A key written to a dropped socket may still have reached the panel,
        # so it is judged like any other.
        for frame in data.decode("ascii").split("$"):
            if frame.startswith("^03,"):
                writer = _writer.get()
                self.key_writes += 1
                self._model.write(writer, frame.rsplit(",", 1)[1])
                if (
                    writer is not None
                    and writer.use == "guided"
                    and writer.written <= len(ENTRY)
                ):
                    self.feed("^03,00$")
                    if writer.written == len(ENTRY):
                        self._model.report("627")
                        self.feed(REPORTS["627"])
                else:
                    self.unacked += 1

    async def drain(self) -> None:
        if self.dropped:
            raise ConnectionResetError

    def close(self) -> None:
        self.dropped = True

    def is_closing(self) -> bool:
        return self.dropped

    async def wait_closed(self) -> None:
        return None

    def feed(self, frames: str) -> None:
        if not self.dropped:
            self.reader.feed_data(frames.encode("ascii"))

    def drop(self) -> None:
        self.dropped = True
        self.reader.feed_eof()


class Run:
    """Applies generated steps to the integration and the model together."""

    def __init__(self, hass: Any) -> None:
        self.hass = hass
        self.model = Model()
        self.entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "host": "127.0.0.1",
                "port": 4025,
                "password": "user",
                "panel_model": "vista_21ip",
                "num_partitions": TRACKED,
                "num_zones": 8,
            },
            options={"installer_code": INSTALLER_CODE},
        )
        self.sessions: list[Session] = []
        self.coordinator: VistaConsoleCoordinator

    async def _open(self, _host: str, _port: int) -> tuple[Any, Any]:
        session = Session(self.model)
        self.sessions.append(session)
        return session.reader, session

    async def start_coordinator(self) -> None:
        coordinator = VistaConsoleCoordinator(
            self.hass,
            self.entry,
            host="127.0.0.1",
            port=4025,
            password="user",
            num_partitions=TRACKED,
            num_zones=8,
            installer_code=INSTALLER_CODE,
        )
        stored = await coordinator._mode_store.async_load()
        if stored is not None:
            coordinator._mode = ModeState.restore(stored)
            coordinator._sync_mode()
        coordinator.client = EnvisalinkClient(
            "127.0.0.1",
            4025,
            "user",
            event_callback=coordinator._handle_event,
            disconnect_callback=coordinator._handle_disconnect,
            open_connection=self._open,
        )
        # Reconnects are steps of their own, not a timed loop.
        coordinator._session_released = True
        await coordinator.client.connect()
        coordinator.data.system.connected = True
        self.coordinator = coordinator
        for number in range(1, TRACKED + 1):
            self.sessions[-1].feed(REPORTS[f"disarmed {number}"])
            self.model.report(f"disarmed {number}")
        await self.settle()

    async def settle(self) -> None:
        for _ in range(SETTLE_TURNS):
            await asyncio.sleep(0)

    def _launch(self, use: str) -> None:
        writer = Writer(use)
        coordinator = self.coordinator

        async def body() -> None:
            _writer.set(writer)
            if use == "everyday":
                await coordinator.async_disarm(1, "1234")
            elif use == "guided":
                await field_programming_services.async_program_function_key(
                    coordinator,
                    key=FunctionKeyLetter.A,
                    partition=1,
                    action=FunctionKeyAction(3),
                )
            else:
                await async_send_guarded_keystrokes(
                    coordinator, 1, ENTRY, allow_installer_mode=True
                )

        async def run() -> None:
            # A refusal is an outcome here; the model judges the keys.
            try:
                await body()
            except Exception:  # noqa: BLE001
                return

        writer.task = asyncio.ensure_future(run())
        self.model.writers.append(writer)

    async def _cancel_writers(self) -> None:
        for writer in self.model.writers:
            if writer.task is not None and not writer.task.done():
                writer.task.cancel()
        await self.settle()

    async def step(self, kind: str, arg: Any) -> None:
        session = self.sessions[-1]
        if kind == "start":
            self._launch(arg)
        elif kind == "ack":
            if session.unacked and not session.dropped:
                session.unacked -= 1
                if arg == "02":
                    self.model.refused_keys += 1
                session.feed(f"^03,{arg}$")
        elif kind == "cancel":
            running = [w for w in self.model.writers if w.running]
            if running:
                task = running[arg % len(running)].task
                assert task is not None
                task.cancel()
        elif kind == "report":
            if not session.dropped:
                self.model.report(arg)
                session.feed(REPORTS[arg])
        elif kind == "drop":
            if not session.dropped:
                self.model.session_ended()
                session.drop()
        elif kind == "reconnect":
            if session.dropped:
                await self.settle()
                await self.coordinator.client.connect()
                self.coordinator.data.system.connected = True
                self.coordinator._transition(ModeEvent.RECONNECT)
                self.model.changes += 1
                for number in range(1, TRACKED + 1):
                    self.sessions[-1].feed(REPORTS[f"disarmed {number}"])
        elif kind == "reload":
            if not session.dropped:
                self.model.session_ended()
            await self.coordinator.async_shutdown()
            # A new coordinator finds a stored doubt; an open report was the
            # old session's. Arm states are unknown again until reported,
            # which the hardware test checks (see TROUBLESHOOTING.md).
            self.model.armed.clear()
            await self.start_coordinator()
        elif kind == "repair":
            self.model.repairs_tried += 1
            generation = (
                self.coordinator._mode.generation if arg == "current" else "old"
            )
            try:
                await self.coordinator.async_confirm_program_mode_closed(
                    str(generation)
                )
            except ValueError:
                pass
            else:
                if not self.model.holder_has_typed() and arg == "current":
                    self.model.set(ProgramMode.CLOSED)
                    self.model.panel_open = False
                    self.model.saw_627 = False
        await self.settle()

    async def finish(self) -> None:
        await self._cancel_writers()
        await self.coordinator.async_shutdown()
        ir.async_delete_issue(self.hass, DOMAIN, self.coordinator.program_mode_issue_id)
        await self.settle()


async def _play(hass: Any, steps: list[tuple[str, Any]]) -> tuple[int, int, int, int]:
    run = Run(hass)
    await run.start_coordinator()
    try:
        # Reach the first menu key on every example. Later generated steps
        # interleave with its held acknowledgement and any queued writers.
        await run.step("start", "guided")
        assert run.model.entry_gates >= len(ENTRY)
        assert run.model.keys_after_entry >= 1
        for number, (kind, arg) in enumerate(steps):
            await run.step(kind, arg)
            assert not run.model.violations, (number, run.model.violations)
        return (
            run.model.entry_gates,
            run.model.keys_after_entry,
            run.model.refused_keys,
            run.model.repairs_tried,
        )
    finally:
        await run.finish()


async def test_no_key_is_written_outside_the_state_the_reports_allow(hass):
    """Every interleaving keeps the keys and the stored state within the rules."""

    counts = [0, 0, 0, 0]

    @settings(
        derandomize=True,
        deadline=None,
        database=None,
        max_examples=80,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    @example([("report", "627"), ("ack", "00")])
    @given(st.lists(STEPS, max_size=25))
    def check(steps: list[tuple[str, Any]]) -> None:
        result = asyncio.run_coroutine_threadsafe(_play(hass, steps), hass.loop).result(
            15
        )
        for index, count in enumerate(result):
            counts[index] += count

    await hass.async_add_executor_job(check)
    assert all(count > 0 for count in counts)
    print(
        f"property coverage: entry gates={counts[0]}, keys after entry={counts[1]}, "
        f"refused keys={counts[2]}, repairs tried={counts[3]}"
    )
