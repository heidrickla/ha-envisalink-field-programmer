"""Random interleavings of what the panel and the user can do around Program Mode.

Hypothesis generates sequences of panel reports (627, 628, armed and disarmed
partitions, tracked, untracked and garbled), acknowledgements held and
released late, writers cancelled while their ack is owed, dropped sessions,
reconnects, reloads, repairs opened earlier and submitted later, and everyday,
guided and installer writers. They run against the real coordinator, started
by its own async_setup, and the real client over an in-memory session.

A reference model folds the same steps by the rules in PROGRAM_MODE_STATE.md,
without reading the integration's state. Every keypress is checked at its write
against the model, and after every step the integration's Program Mode and
whether it saw a 627 must equal the model's.
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
    ModeRefusal,
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
    st.tuples(st.just("ack"), st.sampled_from(["00", "00", "00", "01", "02"])),
    st.tuples(st.just("cancel"), st.integers(0, 3)),
    st.tuples(st.just("report"), st.sampled_from(sorted(REPORTS))),
    st.tuples(st.just("report"), st.sampled_from(["627", "628"])),
    st.tuples(st.just("drop"), st.just(0)),
    st.tuples(st.just("reconnect"), st.just(0)),
    st.tuples(st.just("reload"), st.just(0)),
    st.tuples(st.just("crash"), st.just(0)),
    st.tuples(st.just("snapshot"), st.just(0)),
    st.tuples(st.just("repair"), st.sampled_from(["current", "old", "snapshot"])),
)

_writer: contextvars.ContextVar[Writer | None] = contextvars.ContextVar(
    "writer", default=None
)


@dataclass
class Writer:
    use: str
    task: asyncio.Task[None] | None = None
    # The model has seen this writer take the keypad, and see it finish.
    started: bool = False
    ended: bool = False
    # Keys the module accepted, and whether one is in flight (written, and
    # neither accepted nor refused yet). A refused key is taken back out.
    acked: int = 0
    inflight: bool = False
    # Whether this writer's start raised the doubt, and the model's change
    # count then and when the panel reported this writer's entry open.
    raised: bool = False
    raised_at: int | None = None
    opened_at: int | None = None

    @property
    def running(self) -> bool:
        return self.task is not None and not self.task.done()

    @property
    def attempted(self) -> int:
        return self.acked + (1 if self.inflight else 0)


@dataclass
class Model:
    """What the documented rules say Program Mode is, from the steps alone."""

    state: ProgramMode = ProgramMode.CLOSED
    saw_627: bool = False
    changes: int = 0
    armed: dict[int, bool] = field(default_factory=dict)
    fresh: set[int] = field(default_factory=set)
    # The writer the state's operation id belongs to, if any.
    bound_to: Writer | None = None
    writers: list[Writer] = field(default_factory=list)
    violations: list[str] = field(default_factory=list)
    panel_open: bool = False
    snapshot_changes: int | None = None
    entry_gates: int = 0
    keys_after_entry: int = 0
    refused_keys: int = 0
    repairs_tried: int = 0
    reverts: int = 0
    installer_past_627: int = 0
    stale_repairs: int = 0
    restored_open: int = 0

    def bump(self) -> None:
        self.changes += 1

    def holder(self) -> Writer | None:
        for w in self.writers:
            if w.started and not w.ended:
                return w
        return None

    # -- Writers take the keypad one at a time, in the order they asked ------

    def advance(self) -> None:
        """Start and end writers as far as the integration has taken them."""
        for w in self.writers:
            if w.ended:
                continue
            if not w.started and not self.start(w):
                continue
            if w.task is not None and w.task.done():
                self.end(w)
                continue
            break

    def start(self, w: Writer) -> bool:
        """Operation start. A refused start changes nothing and ends the writer."""
        w.started = True
        if w.use == "installer":
            if self.state is ProgramMode.CLOSED:
                self.state = ProgramMode.DOUBT
                self.saw_627 = False
                w.raised = True
            self.bound_to = w
            self.bump()
            w.raised_at = self.changes
            return True
        closed = self.state is ProgramMode.CLOSED
        if w.use == "everyday":
            refused = not closed or 1 not in self.fresh
        else:
            refused = (
                not closed
                or self.fresh != set(range(1, TRACKED + 1))
                or any(self.armed.values())
            )
        if refused:
            w.ended = True
            return False
        if w.use == "guided":
            self.state = ProgramMode.DOUBT
            self.saw_627 = False
            w.raised = True
            self.bound_to = w
            self.bump()
            w.raised_at = self.changes
        return True

    def end(self, w: Writer) -> None:
        """Operation end; a doubt raised for keys that never went out is dropped."""
        w.ended = True
        if w.use == "everyday":
            return
        if w.attempted == 0:
            self.no_key_sent(w)
        if self.bound_to is w:
            if self.state is ProgramMode.OPEN:
                self.state = ProgramMode.DOUBT
                self.saw_627 = True
            self.bound_to = None
            self.bump()
        elif self.state is ProgramMode.OPEN and self.bound_to is None:
            self.state = ProgramMode.DOUBT
            self.saw_627 = True
            self.bump()

    def no_key_sent(self, w: Writer) -> None:
        if (
            self.state is ProgramMode.DOUBT
            and self.bound_to is w
            and w.raised
            and not self.saw_627
        ):
            self.state = ProgramMode.CLOSED
            self.bound_to = None
            self.bump()
            self.reverts += 1

    # -- What the panel and the module say ----------------------------------

    def report(self, name: str) -> None:
        self.advance()
        if name == "627":
            h = self.holder()
            explained = False
            if h is not None and self.bound_to is h:
                if h.use == "installer":
                    explained = h.attempted > 0
                else:
                    explained = (
                        self.state is ProgramMode.DOUBT
                        and h.attempted >= len(ENTRY)
                        and h.acked >= len(ENTRY) - 1
                    )
            self.state = ProgramMode.OPEN
            self.saw_627 = True
            self.panel_open = True
            self.bound_to = h if explained else None
            self.bump()
            # A guided entry's own 627 is the one change after its doubt.
            if (
                explained
                and h is not None
                and h.use == "guided"
                and h.raised_at is not None
                and self.changes == h.raised_at + 1
            ):
                h.opened_at = self.changes
        elif name == "628":
            self.state = ProgramMode.CLOSED
            self.saw_627 = False
            self.panel_open = False
            self.bound_to = None
            self.bump()
        else:
            kind, _, number = name.partition(" ")
            if not number.isdigit() or not 1 <= int(number) <= TRACKED:
                return
            self.armed[int(number)] = kind == "armed"
            self.fresh.add(int(number))
            if (
                kind == "armed"
                and self.state is ProgramMode.DOUBT
                and not self.saw_627
                and self.bound_to is None
                and self.holder() is None
            ):
                self.state = ProgramMode.CLOSED
                self.bump()

    def ack(self, w: Writer | None, response: str) -> None:
        """The module's answer to the key in flight."""
        self.advance()
        if w is None or not w.inflight:
            return
        if response == "00":
            w.acked += 1
            w.inflight = False
        elif response == "02":
            w.inflight = False
            self.refused_keys += 1
        # 01 is an overrun: the same key is written again.

    def session_ended(self) -> None:
        # A change either way: keys belong to the session their entry used.
        self.advance()
        if self.state is ProgramMode.OPEN:
            self.state = ProgramMode.DOUBT
        self.bump()
        self.fresh.clear()

    def confirm_closed(self) -> None:
        self.state = ProgramMode.CLOSED
        self.saw_627 = False
        self.panel_open = False
        self.bound_to = None
        self.bump()

    # -- Keys, checked at the instant they are written ----------------------

    def write(self, w: Writer | None, key: str) -> None:
        self.advance()
        if w is None:
            self.violations.append(f"key {key!r} written by no writer")
            return
        if not w.inflight:
            index = w.acked
            w.inflight = True
        else:
            index = w.acked
        where = f"{w.use} key {index} ({key!r}) in {self.state.value}"
        if w.use == "everyday":
            if self.panel_open or self.state is not ProgramMode.CLOSED:
                self.violations.append(where)
        elif w.use == "installer":
            if self.bound_to is not w:
                self.violations.append(where + " outside its own binding")
            elif self.state is ProgramMode.OPEN:
                self.installer_past_627 += 1
        elif index < len(ENTRY):
            self.entry_gates += 1
            if any(self.armed.values()):
                self.violations.append(where + " with a partition armed")
            if not (
                self.state is ProgramMode.DOUBT
                and self.bound_to is w
                and self.changes == w.raised_at
            ):
                self.violations.append(where + " after the state changed")
        else:
            self.keys_after_entry += 1
            if not (
                self.state is ProgramMode.OPEN
                and self.bound_to is w
                and self.changes == w.opened_at
            ):
                self.violations.append(where + " outside its own Program Mode")


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
                self._key(frame)
            elif frame.startswith("^01,"):
                self._partition_request(int(frame[4:]))
            elif frame.startswith("^"):
                self.feed(f"{frame[:3]},00$")

    def _key(self, frame: str) -> None:
        writer = _writer.get()
        self.key_writes += 1
        self._model.write(writer, frame.rsplit(",", 1)[1])
        if writer is not None and writer.use == "guided" and writer.acked < len(ENTRY):
            # The panel takes the entry keys, and reports Program Mode after
            # the last of them in the same write as its acknowledgement.
            self.feed("^03,00$")
            if writer.acked == len(ENTRY) - 1:
                self._model.report("627")
                self.feed(REPORTS["627"])
            self._model.ack(writer, "00")
        else:
            self.unacked += 1

    def _partition_request(self, partition: int) -> None:
        """^01 changes the default partition; the panel answers with its keypad."""
        self.feed("^01,00$")
        if 1 <= partition <= TRACKED:
            name = f"{'armed' if self._model.armed.get(partition) else 'disarmed'} {partition}"
            self._model.report(name)
            self.feed(REPORTS[name])

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
        # What a repair flow opened earlier holds: the doubt it was opened for.
        self.snapshot: tuple[str, int] | None = None

    async def _open(self, _host: str, _port: int) -> tuple[Any, Any]:
        session = Session(self.model)
        self.sessions.append(session)
        return session.reader, session

    async def start_coordinator(self) -> None:
        """Start the coordinator as Home Assistant does, restore path included."""
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
        self.coordinator = coordinator
        await coordinator.async_setup()
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
        self.model.advance()
        for writer in self.model.writers:
            if writer.running:
                if not writer.started:
                    writer.ended = True
                writer.task.cancel()  # type: ignore[union-attr]
        await self.settle()
        self.model.advance()

    async def step(self, kind: str, arg: Any) -> None:
        model = self.model
        session = self.sessions[-1]
        model.advance()
        if kind == "start":
            self._launch(arg)
        elif kind == "ack":
            if session.unacked and not session.dropped:
                session.unacked -= 1
                holder = model.holder()
                session.feed(f"^03,{arg}$")
                model.ack(holder, arg)
        elif kind == "cancel":
            running = [w for w in model.writers if w.running]
            if running:
                chosen = running[arg % len(running)]
                if not chosen.started:
                    chosen.ended = True
                assert chosen.task is not None
                chosen.task.cancel()
        elif kind == "report":
            if not session.dropped:
                model.report(arg)
                session.feed(REPORTS[arg])
        elif kind == "drop":
            if not session.dropped:
                model.session_ended()
                session.drop()
        elif kind == "reconnect":
            if session.dropped:
                await self.settle()
                model.advance()
                model.bump()
                self.coordinator._session_released = False
                await self.coordinator.async_resume_session()
                self.coordinator._session_released = True
        elif kind in ("reload", "crash"):
            await self._cancel_writers()
            if kind == "crash":
                # Nothing folds the dying session, so the store keeps what it
                # last held, an open Program Mode included.
                self.coordinator.client._disconnect_callback = None
                if model.state is ProgramMode.OPEN:
                    model.restored_open += 1
                    model.state = ProgramMode.DOUBT
            elif not session.dropped:
                model.session_ended()
            await self.coordinator.async_shutdown()
            # Restoring and the reload fold each advance the revision.
            model.bump()
            model.bump()
            model.fresh.clear()
            await self.start_coordinator()
        elif kind == "snapshot":
            mode = self.coordinator._mode
            self.snapshot = (str(mode.generation), mode.revision)
            model.snapshot_changes = model.changes
        elif kind == "repair":
            await self._submit_repair(arg)
        await self.settle()
        model.advance()

    async def _submit_repair(self, which: str) -> None:
        model = self.model
        model.advance()
        mode = self.coordinator._mode
        if which == "snapshot":
            if self.snapshot is None:
                return
            generation, revision = self.snapshot
            fits = model.changes == model.snapshot_changes
        elif which == "current":
            generation, revision = str(mode.generation), mode.revision
            fits = True
        else:
            generation, revision = "old", mode.revision
            fits = False
        model.repairs_tried += 1
        expected = (
            fits
            and model.holder() is None
            and model.bound_to is None
            and model.state is not ProgramMode.CLOSED
        )
        try:
            await self.coordinator.async_confirm_program_mode_closed(
                generation, revision
            )
        except ModeRefusal:
            accepted = False
        else:
            accepted = True
        if accepted != expected:
            model.violations.append(
                f"repair {which}: integration accepted={accepted}, rules say {expected}"
            )
        if accepted:
            model.confirm_closed()
        elif which == "snapshot" and not fits:
            model.stale_repairs += 1

    def disagreement(self) -> str | None:
        """Where the integration's state differs from the model's, if it does."""
        self.model.advance()
        mode = self.coordinator.program_mode
        saw = self.coordinator._mode.saw_627
        expected_saw = self.model.saw_627 and self.model.state is not ProgramMode.CLOSED
        if (mode, saw) != (self.model.state, expected_saw):
            return (
                f"integration {mode.value} saw_627={saw}, "
                f"model {self.model.state.value} saw_627={expected_saw}"
            )
        return None

    async def finish(self) -> None:
        await self._cancel_writers()
        await self.coordinator.async_shutdown()
        ir.async_delete_issue(self.hass, DOMAIN, self.coordinator.program_mode_issue_id)
        await self.settle()


async def _play(hass: Any, steps: list[tuple[str, Any]]) -> tuple[int, ...]:
    run = Run(hass)
    await run.start_coordinator()
    try:
        assert run.disagreement() is None, run.disagreement()
        # Reach the first menu key on every example. Later generated steps
        # interleave with its held acknowledgement and any queued writers.
        await run.step("start", "guided")
        assert run.model.entry_gates >= len(ENTRY)
        assert run.model.keys_after_entry >= 1
        for number, (kind, arg) in enumerate(steps):
            await run.step(kind, arg)
            assert not run.model.violations, (number, kind, arg, run.model.violations)
            assert run.disagreement() is None, (number, kind, arg, run.disagreement())
        model = run.model
        return (
            model.entry_gates,
            model.keys_after_entry,
            model.refused_keys,
            model.repairs_tried,
            model.reverts,
            model.installer_past_627,
            model.stale_repairs,
            model.restored_open,
        )
    finally:
        await run.finish()


async def test_no_key_is_written_outside_the_state_the_reports_allow(hass, monkeypatch):
    """Every interleaving keeps the keys and the stored state within the rules."""

    # A silent partition is refused at once here; the session answers every
    # request itself, so only a dropped session leaves one unreported.
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator."
        "PARTITION_REPORT_TIMEOUT",
        0,
    )
    counts = [0] * 8

    @settings(
        derandomize=True,
        deadline=None,
        database=None,
        max_examples=80,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
    )
    @example([("report", "627"), ("ack", "00")])
    # An installer that types past the 627 its own keys produced.
    @example(
        [
            ("cancel", 0),
            ("report", "628"),
            ("start", "installer"),
            ("ack", "00"),
            ("report", "627"),
            ("ack", "00"),
            ("ack", "00"),
        ]
    )
    # A doubt raised for keys that never went out is dropped.
    @example(
        [
            ("cancel", 0),
            ("report", "628"),
            ("start", "installer"),
            ("cancel", 0),
        ]
    )
    # A repair opened earlier is stale once the state moved on.
    @example(
        [
            ("cancel", 0),
            ("snapshot", 0),
            ("report", "627"),
            ("repair", "snapshot"),
            ("repair", "current"),
        ]
    )
    # A stored OPEN, left by a crash, is restored as a doubt that saw a 627.
    @example(
        [
            ("cancel", 0),
            ("report", "628"),
            ("report", "627"),
            ("crash", 0),
            ("report", "628"),
        ]
    )
    @given(st.lists(STEPS, max_size=25))
    def check(steps: list[tuple[str, Any]]) -> None:
        result = asyncio.run_coroutine_threadsafe(_play(hass, steps), hass.loop).result(
            15
        )
        for index, count in enumerate(result):
            counts[index] += count

    await hass.async_add_executor_job(check)
    assert all(count > 0 for count in counts), counts
    print(
        f"property coverage: entry gates={counts[0]}, keys after entry={counts[1]}, "
        f"refused keys={counts[2]}, repairs tried={counts[3]}, "
        f"doubts dropped={counts[4]}, installer keys past a 627={counts[5]}, "
        f"stale repairs={counts[6]}, stored OPEN restored={counts[7]}"
    )
