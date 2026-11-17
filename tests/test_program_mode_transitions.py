"""The transition table in PROGRAM_MODE_STATE.md, one test case per cell.

Every row of the table is a ModeEvent and every column a ProgramMode. The cases
below are the table: a change to a rule is a change to PROGRAM_MODE_STATE.md,
to the matching case here, and to program_mode_state.py, and a rule that is
deleted from the function leaves a case red.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import pytest

from custom_components.envisalink_field_programmer import program_mode_state as pms
from custom_components.envisalink_field_programmer.models import ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import (
    ModeEvent,
    ModeState,
    transition,
)

CLOSED = ProgramMode.CLOSED
OPEN = ProgramMode.OPEN
DOUBT = ProgramMode.DOUBT

# The first column of the table in PROGRAM_MODE_STATE.md.
ROW_LABELS: dict[ModeEvent, str] = {
    ModeEvent.OPERATION_START: "Operation start",
    ModeEvent.KEY_WRITE: "Key write",
    ModeEvent.NO_KEY_SENT: "No key sent",
    ModeEvent.OPEN_REPORT: "627",
    ModeEvent.CLOSE_REPORT: "628",
    ModeEvent.ARMED_REPORT: "Armed report for a tracked partition",
    ModeEvent.DISARMED_REPORT: "Disarmed report",
    ModeEvent.DISCONNECT: "Disconnect",
    ModeEvent.RECONNECT: "Reconnect",
    ModeEvent.RELOAD: "Reload or restart",
    ModeEvent.REPAIR_CONFIRM: "Repair confirm",
    ModeEvent.OPERATION_END: "Operation end",
}

REVISION = 3
NEXT = REVISION + 1


def closed(**kw: object) -> ModeState:
    return ModeState(CLOSED, None, kw.get("op"), False, REVISION)  # type: ignore[arg-type]


def opened(op: str | None = None, *, gen: str = "g") -> ModeState:
    return ModeState(OPEN, gen, op, True, REVISION)


def doubt(op: str | None = None, *, saw: bool = False, gen: str = "g") -> ModeState:
    return ModeState(DOUBT, gen, op, saw, REVISION)


@dataclass
class Case:
    name: str
    event: ModeEvent
    state: ModeState
    kwargs: dict[str, object] = field(default_factory=dict)
    # Either the whole expected state, or the refusal's reason.
    after: ModeState | None = None
    refused: str | None = None


def unchanged(state: ModeState) -> ModeState:
    return state


def bumped(state: ModeState, **changes: object) -> ModeState:
    return replace(state, revision=NEXT, **changes)  # type: ignore[arg-type]


def guided_holder(
    *, length: int = 7, sent: int = 7, written: int = 6, op: str = "op"
) -> pms.Holder:
    return pms.Holder(
        op, installer=False, entry_length=length, entry_sent=sent, written=written
    )


def installer_holder(*, attempted: int = 1, op: str = "op") -> pms.Holder:
    return pms.Holder(op, installer=True, attempted=attempted)


CASES: list[Case] = [
    # -- Operation start ----------------------------------------------------
    Case(
        "start guided from CLOSED",
        ModeEvent.OPERATION_START,
        closed(),
        {"operation_id": "op"},
        after=ModeState(DOUBT, "*", "op", False, NEXT),
    ),
    Case(
        "start installer from CLOSED",
        ModeEvent.OPERATION_START,
        closed(),
        {"operation_id": "op", "installer": True},
        after=ModeState(DOUBT, "*", "op", False, NEXT),
    ),
    Case(
        "start ordinary from CLOSED",
        ModeEvent.OPERATION_START,
        closed(),
        {"operation_id": "op", "everyday": True},
        after=closed(),
    ),
    Case(
        "start guided from OPEN",
        ModeEvent.OPERATION_START,
        opened(),
        {"operation_id": "op"},
        refused="not_closed",
    ),
    Case(
        "start ordinary from OPEN",
        ModeEvent.OPERATION_START,
        opened(),
        {"operation_id": "op", "everyday": True},
        refused="not_closed",
    ),
    Case(
        "start installer from OPEN",
        ModeEvent.OPERATION_START,
        opened(),
        {"operation_id": "op", "installer": True},
        after=bumped(opened(), operation_id="op"),
    ),
    Case(
        "start guided from DOUBT",
        ModeEvent.OPERATION_START,
        doubt(),
        {"operation_id": "op"},
        refused="not_closed",
    ),
    Case(
        "start ordinary from DOUBT",
        ModeEvent.OPERATION_START,
        doubt(),
        {"operation_id": "op", "everyday": True},
        refused="not_closed",
    ),
    Case(
        "start installer from DOUBT",
        ModeEvent.OPERATION_START,
        doubt(saw=True),
        {"operation_id": "op", "installer": True},
        after=bumped(doubt(saw=True), operation_id="op"),
    ),
    Case(
        "start while another operation holds",
        ModeEvent.OPERATION_START,
        doubt("other"),
        {"operation_id": "op", "installer": True},
        refused="held",
    ),
    # -- Key write ----------------------------------------------------------
    Case("ordinary key in CLOSED", ModeEvent.KEY_WRITE, closed(), after=closed()),
    Case(
        "guided key in CLOSED without its doubt",
        ModeEvent.KEY_WRITE,
        closed(),
        {"operation_id": "op"},
        refused="not_owner",
    ),
    Case("ordinary key in OPEN", ModeEvent.KEY_WRITE, opened(), refused="not_closed"),
    Case(
        "guided menu key in OPEN",
        ModeEvent.KEY_WRITE,
        opened("op"),
        {"operation_id": "op", "entry_complete": True},
        after=opened("op"),
    ),
    Case(
        "guided entry key in OPEN",
        ModeEvent.KEY_WRITE,
        opened("op"),
        {"operation_id": "op"},
        refused="entry_after_open",
    ),
    Case(
        "guided menu key of another operation in OPEN",
        ModeEvent.KEY_WRITE,
        opened("other"),
        {"operation_id": "op", "entry_complete": True},
        refused="not_owner",
    ),
    Case(
        "installer key in OPEN by its holder",
        ModeEvent.KEY_WRITE,
        opened("op"),
        {"operation_id": "op", "installer": True},
        after=opened("op"),
    ),
    Case(
        "installer key in OPEN by another",
        ModeEvent.KEY_WRITE,
        opened("other"),
        {"operation_id": "op", "installer": True},
        refused="not_owner",
    ),
    Case("ordinary key in DOUBT", ModeEvent.KEY_WRITE, doubt(), refused="not_closed"),
    Case(
        "guided entry key in DOUBT",
        ModeEvent.KEY_WRITE,
        doubt("op"),
        {"operation_id": "op"},
        after=doubt("op"),
    ),
    Case(
        "guided menu key in DOUBT",
        ModeEvent.KEY_WRITE,
        doubt("op"),
        {"operation_id": "op", "entry_complete": True},
        refused="menu_before_open",
    ),
    Case(
        "installer key in DOUBT by its holder",
        ModeEvent.KEY_WRITE,
        doubt("op"),
        {"operation_id": "op", "installer": True},
        after=doubt("op"),
    ),
    Case(
        "installer key in DOUBT by another",
        ModeEvent.KEY_WRITE,
        doubt("other"),
        {"operation_id": "op", "installer": True},
        refused="not_owner",
    ),
    # -- No key sent --------------------------------------------------------
    Case(
        "no key in CLOSED",
        ModeEvent.NO_KEY_SENT,
        closed(),
        {"operation_id": "op", "generation": "g"},
        after=closed(),
    ),
    Case(
        "no key in OPEN",
        ModeEvent.NO_KEY_SENT,
        opened("op"),
        {"operation_id": "op", "generation": "g"},
        after=opened("op"),
    ),
    Case(
        "no key in the operation's own DOUBT",
        ModeEvent.NO_KEY_SENT,
        doubt("op"),
        {"operation_id": "op", "generation": "g"},
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    Case(
        "no key but a 627 was seen",
        ModeEvent.NO_KEY_SENT,
        doubt("op", saw=True),
        {"operation_id": "op", "generation": "g"},
        after=doubt("op", saw=True),
    ),
    Case(
        "no key in a doubt that existed before the operation",
        ModeEvent.NO_KEY_SENT,
        doubt("op", gen="old"),
        {"operation_id": "op", "generation": "g"},
        after=doubt("op", gen="old"),
    ),
    Case(
        "no key from an operation that does not hold the doubt",
        ModeEvent.NO_KEY_SENT,
        doubt("other"),
        {"operation_id": "op", "generation": "g"},
        after=doubt("other"),
    ),
    # -- 627 ----------------------------------------------------------------
    Case(
        "627 in CLOSED binds to nobody",
        ModeEvent.OPEN_REPORT,
        closed(),
        {"holder": guided_holder()},
        after=ModeState(OPEN, "*", None, True, NEXT),
    ),
    Case(
        "627 in CLOSED with no holder",
        ModeEvent.OPEN_REPORT,
        closed(),
        after=ModeState(OPEN, "*", None, True, NEXT),
    ),
    Case(
        "627 in DOUBT after the guided entry",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": guided_holder()},
        after=bumped(opened("op")),
    ),
    Case(
        "627 in DOUBT after the entry's last key was sent but not yet acknowledged",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": guided_holder(sent=7, written=6)},
        after=bumped(opened("op")),
    ),
    Case(
        "627 in DOUBT before the guided entry's last key",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": guided_holder(sent=6, written=6)},
        after=bumped(opened()),
    ),
    Case(
        "627 in DOUBT with the entry not acknowledged far enough",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": guided_holder(sent=7, written=3)},
        after=bumped(opened()),
    ),
    Case(
        "627 in DOUBT before the guided operation has an entry length",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": guided_holder(length=0, sent=0, written=0)},
        after=bumped(opened()),
    ),
    Case(
        "627 in DOUBT for another operation",
        ModeEvent.OPEN_REPORT,
        doubt("other"),
        {"holder": guided_holder()},
        after=bumped(opened()),
    ),
    Case(
        "627 in DOUBT with no holder",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        after=bumped(opened()),
    ),
    Case(
        "627 in DOUBT after an installer key began",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": installer_holder()},
        after=bumped(opened("op")),
    ),
    Case(
        "627 in DOUBT before any installer key",
        ModeEvent.OPEN_REPORT,
        doubt("op"),
        {"holder": installer_holder(attempted=0)},
        after=bumped(opened()),
    ),
    Case(
        "second 627 invalidates a guided binding",
        ModeEvent.OPEN_REPORT,
        opened("op"),
        {"holder": guided_holder()},
        after=bumped(opened()),
    ),
    Case(
        "second 627 keeps an installer binding",
        ModeEvent.OPEN_REPORT,
        opened("op"),
        {"holder": installer_holder()},
        after=bumped(opened("op")),
    ),
    Case(
        "second 627 in OPEN with no holder",
        ModeEvent.OPEN_REPORT,
        opened(),
        after=bumped(opened()),
    ),
    # -- 628 ----------------------------------------------------------------
    Case(
        "628 in CLOSED",
        ModeEvent.CLOSE_REPORT,
        closed(),
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    Case(
        "628 in OPEN ends the binding",
        ModeEvent.CLOSE_REPORT,
        opened("op"),
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    Case(
        "628 in DOUBT ends the binding",
        ModeEvent.CLOSE_REPORT,
        doubt("op", saw=True),
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    # -- Armed report -------------------------------------------------------
    Case("armed in CLOSED", ModeEvent.ARMED_REPORT, closed(), after=closed()),
    Case("armed in OPEN", ModeEvent.ARMED_REPORT, opened(), after=opened()),
    Case(
        "armed in an idle doubt",
        ModeEvent.ARMED_REPORT,
        doubt(),
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    Case(
        "armed in a doubt while an operation holds the keypad",
        ModeEvent.ARMED_REPORT,
        doubt(),
        {"holding": True},
        after=doubt(),
    ),
    Case(
        "armed in a doubt bound to an operation",
        ModeEvent.ARMED_REPORT,
        doubt("op"),
        after=doubt("op"),
    ),
    Case(
        "armed in a doubt where a 627 was seen",
        ModeEvent.ARMED_REPORT,
        doubt(saw=True),
        after=doubt(saw=True),
    ),
    # -- Disarmed report ----------------------------------------------------
    Case("disarmed in CLOSED", ModeEvent.DISARMED_REPORT, closed(), after=closed()),
    Case("disarmed in OPEN", ModeEvent.DISARMED_REPORT, opened(), after=opened()),
    Case("disarmed in DOUBT", ModeEvent.DISARMED_REPORT, doubt(), after=doubt()),
    # -- Disconnect, reconnect, reload --------------------------------------
    *[
        case
        for event in (ModeEvent.DISCONNECT, ModeEvent.RECONNECT, ModeEvent.RELOAD)
        for case in (
            Case(f"{event.value} in CLOSED", event, closed(), after=bumped(closed())),
            Case(
                f"{event.value} in OPEN",
                event,
                opened("op"),
                after=bumped(doubt("op", saw=True)),
            ),
            Case(
                f"{event.value} in DOUBT",
                event,
                doubt("op", saw=False),
                after=bumped(doubt("op", saw=False)),
            ),
        )
    ],
    # -- Repair confirm -----------------------------------------------------
    Case(
        "confirm in CLOSED",
        ModeEvent.REPAIR_CONFIRM,
        closed(),
        {"generation": "g", "revision": REVISION},
        refused="settled",
    ),
    Case(
        "confirm in OPEN",
        ModeEvent.REPAIR_CONFIRM,
        opened(),
        {"generation": "g", "revision": REVISION},
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    Case(
        "confirm in DOUBT",
        ModeEvent.REPAIR_CONFIRM,
        doubt(),
        {"generation": "g", "revision": REVISION},
        after=ModeState(CLOSED, None, None, False, NEXT),
    ),
    Case(
        "confirm of another generation",
        ModeEvent.REPAIR_CONFIRM,
        doubt(),
        {"generation": "old", "revision": REVISION},
        refused="stale",
    ),
    Case(
        "confirm of an older revision",
        ModeEvent.REPAIR_CONFIRM,
        doubt(),
        {"generation": "g", "revision": REVISION - 1},
        refused="stale",
    ),
    Case(
        "confirm of an older revision in OPEN",
        ModeEvent.REPAIR_CONFIRM,
        opened(),
        {"generation": "g", "revision": REVISION - 1},
        refused="stale",
    ),
    Case(
        "confirm while the keypad is held",
        ModeEvent.REPAIR_CONFIRM,
        doubt(),
        {"generation": "g", "revision": REVISION, "holding": True},
        refused="held",
    ),
    Case(
        "confirm while an operation is bound",
        ModeEvent.REPAIR_CONFIRM,
        doubt("op"),
        {"generation": "g", "revision": REVISION},
        refused="held",
    ),
    # -- Operation end ------------------------------------------------------
    Case(
        "end of a guided operation in CLOSED",
        ModeEvent.OPERATION_END,
        closed(op="op"),
        {"operation_id": "op"},
        after=bumped(closed()),
    ),
    Case(
        "end of an unbound operation in CLOSED",
        ModeEvent.OPERATION_END,
        closed(),
        {"operation_id": "op"},
        after=closed(),
    ),
    Case(
        "end of a guided operation in OPEN",
        ModeEvent.OPERATION_END,
        opened("op"),
        {"operation_id": "op"},
        after=bumped(doubt(saw=True)),
    ),
    Case(
        "end of a guided operation in DOUBT",
        ModeEvent.OPERATION_END,
        doubt("op"),
        {"operation_id": "op"},
        after=bumped(doubt()),
    ),
    Case(
        "end of an unbound operation in an unbound OPEN",
        ModeEvent.OPERATION_END,
        opened(),
        {"operation_id": "op"},
        after=bumped(doubt(saw=True)),
    ),
    Case(
        "end of an unbound operation in DOUBT",
        ModeEvent.OPERATION_END,
        doubt("other"),
        {"operation_id": "op"},
        after=doubt("other"),
    ),
    Case(
        "end of an ordinary operation in OPEN",
        ModeEvent.OPERATION_END,
        opened(),
        {"operation_id": "op", "everyday": True},
        after=opened(),
    ),
    Case(
        "end of an ordinary operation in DOUBT",
        ModeEvent.OPERATION_END,
        doubt(),
        {"operation_id": "op", "everyday": True},
        after=doubt(),
    ),
]


def _normalize(state: ModeState, *, fresh: ModeState) -> ModeState:
    """A new generation is random; the table says only that there is one."""
    if state.generation is not None and fresh.generation == "*":
        return replace(state, generation="*")
    return state


@pytest.mark.parametrize("case", CASES, ids=lambda c: c.name)
def test_every_cell_of_the_table(case: Case) -> None:
    if case.refused is not None:
        with pytest.raises(pms.ModeRefusal) as raised:
            transition(case.state, case.event, **case.kwargs)  # type: ignore[arg-type]
        assert raised.value.reason.value == case.refused
        return
    assert case.after is not None
    after = transition(case.state, case.event, **case.kwargs)  # type: ignore[arg-type]
    assert _normalize(after, fresh=case.after) == case.after


def test_every_state_and_event_pair_has_a_case() -> None:
    covered = {(case.event, case.state.mode) for case in CASES}
    assert covered == {(event, mode) for event in ModeEvent for mode in ProgramMode}


def test_the_table_in_the_document_names_every_event_once() -> None:
    document = (Path(__file__).parent.parent / "PROGRAM_MODE_STATE.md").read_text(
        encoding="utf-8"
    )
    rows = [
        line.split("|")[1].strip()
        for line in document.splitlines()
        if line.startswith("| ")
        and not line.startswith("| Event")
        and not line.startswith("|---")
    ]
    assert rows == list(ROW_LABELS.values())
    assert set(ROW_LABELS) == set(ModeEvent)
    for line in document.splitlines():
        if line.startswith("| ") and not line.startswith("|---"):
            assert len(re.findall(r"\|", line)) == 5


# -- Restore --------------------------------------------------------------


def test_a_stored_open_is_restored_as_a_doubt_that_remembers_the_627() -> None:
    restored = ModeState.restore(
        {
            "mode": "open",
            "generation": "g",
            "operation_id": "old",
            "saw_627": True,
            "revision": 9,
        }
    )
    assert restored.mode is DOUBT
    assert restored.generation == "g"
    assert restored.saw_627
    assert restored.operation_id is None
    assert restored.revision == 10


def test_a_stored_open_without_a_generation_gets_one() -> None:
    restored = ModeState.restore({"mode": "open", "saw_627": True})
    assert restored.mode is DOUBT and restored.generation


def test_a_stored_closed_is_restored_closed_and_a_stored_doubt_stays_a_doubt() -> None:
    assert ModeState.restore({"mode": "closed"}).mode is CLOSED
    assert ModeState.restore({"mode": "closed", "generation": "g"}).generation is None
    kept = ModeState.restore({"mode": "doubt", "generation": "g", "saw_627": True})
    assert (kept.mode, kept.generation, kept.saw_627) == (DOUBT, "g", True)
    assert ModeState.restore({}).mode is DOUBT


def test_stored_state_round_trips() -> None:
    state = doubt("op", saw=True)
    assert ModeState.restore(state.stored()).generation == "g"


def test_everyday_operation_start_and_end_leave_closed_unchanged() -> None:
    started = transition(
        closed(), ModeEvent.OPERATION_START, operation_id="x", everyday=True
    )
    assert started == closed()
    assert (
        transition(started, ModeEvent.OPERATION_END, operation_id="x", everyday=True)
        == closed()
    )
