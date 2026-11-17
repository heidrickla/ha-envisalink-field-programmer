"""Every Program Mode state and event goes through the transition table."""

from __future__ import annotations

import pytest

from custom_components.envisalink_field_programmer.models import ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import (
    ModeEvent,
    ModeState,
    transition,
)

EXPECTED: dict[ModeEvent, tuple[ProgramMode | None, ...]] = {
    ModeEvent.OPERATION_START: (ProgramMode.DOUBT, None, None),
    ModeEvent.KEY_WRITE: (ProgramMode.CLOSED, ProgramMode.OPEN, ProgramMode.DOUBT),
    ModeEvent.OPEN_REPORT: (ProgramMode.OPEN,) * 3,
    ModeEvent.CLOSE_REPORT: (ProgramMode.CLOSED,) * 3,
    ModeEvent.ARMED_REPORT: (ProgramMode.CLOSED, ProgramMode.OPEN, ProgramMode.CLOSED),
    ModeEvent.DISARMED_REPORT: tuple(ProgramMode),
    ModeEvent.DISCONNECT: (ProgramMode.CLOSED, ProgramMode.DOUBT, ProgramMode.DOUBT),
    ModeEvent.RECONNECT: (ProgramMode.CLOSED, ProgramMode.DOUBT, ProgramMode.DOUBT),
    ModeEvent.RELOAD: (ProgramMode.CLOSED, ProgramMode.DOUBT, ProgramMode.DOUBT),
    ModeEvent.REPAIR_CONFIRM: (None, ProgramMode.CLOSED, ProgramMode.CLOSED),
    ModeEvent.OPERATION_END: (ProgramMode.CLOSED, ProgramMode.DOUBT, ProgramMode.DOUBT),
    ModeEvent.KEY_REFUSED: (ProgramMode.CLOSED, ProgramMode.OPEN, ProgramMode.CLOSED),
}


@pytest.mark.parametrize("event", list(ModeEvent))
@pytest.mark.parametrize("mode", list(ProgramMode))
def test_every_state_event_pair(mode: ProgramMode, event: ModeEvent) -> None:
    index = list(ProgramMode).index(mode)
    operation = (
        "op"
        if event
        in {ModeEvent.KEY_WRITE, ModeEvent.OPERATION_END, ModeEvent.KEY_REFUSED}
        else None
    )
    state = ModeState(
        mode,
        "generation" if mode is not ProgramMode.CLOSED else None,
        operation,
        False,
        3,
    )
    kwargs: dict[str, object] = {}
    if event in {
        ModeEvent.OPERATION_START,
        ModeEvent.KEY_WRITE,
        ModeEvent.OPERATION_END,
        ModeEvent.KEY_REFUSED,
    }:
        kwargs["operation_id"] = "op"
    if event is ModeEvent.KEY_WRITE:
        kwargs["entry_complete"] = mode is ProgramMode.OPEN
    if event is ModeEvent.REPAIR_CONFIRM:
        kwargs["generation"] = "generation"
    expected = EXPECTED[event][index]
    if expected is None:
        with pytest.raises(ValueError):
            transition(state, event, **kwargs)  # type: ignore[arg-type]
    else:
        after = transition(state, event, **kwargs)  # type: ignore[arg-type]
        assert after.mode is expected


def test_reported_open_doubt_survives_armed_and_disconnect() -> None:
    doubt = transition(
        ModeState(ProgramMode.OPEN, "g", "op", True, 1), ModeEvent.DISCONNECT
    )
    assert doubt.mode is ProgramMode.DOUBT
    assert doubt.saw_627
    assert transition(doubt, ModeEvent.ARMED_REPORT).mode is ProgramMode.DOUBT
    restored = ModeState.restore(doubt.stored())
    assert restored.generation == "g" and restored.saw_627


def test_stale_or_held_repair_cannot_close_doubt() -> None:
    doubt = ModeState(ProgramMode.DOUBT, "current", None, False, 1)
    for kwargs in ({"generation": "old"}, {"generation": "current", "holding": True}):
        with pytest.raises(ValueError):
            transition(doubt, ModeEvent.REPAIR_CONFIRM, **kwargs)  # type: ignore[arg-type]


def test_everyday_operation_start_and_end_leave_closed_unchanged() -> None:
    closed = ModeState()
    started = transition(
        closed, ModeEvent.OPERATION_START, operation_id="ordinary", everyday=True
    )
    assert started == closed
    assert (
        transition(
            started, ModeEvent.OPERATION_END, operation_id="ordinary", everyday=True
        )
        == closed
    )
