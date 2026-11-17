"""The single transition function for panel Program Mode evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4

from .models import ProgramMode


class ModeEvent(Enum):
    OPERATION_START = "operation_start"
    KEY_WRITE = "key_write"
    OPEN_REPORT = "627"
    CLOSE_REPORT = "628"
    ARMED_REPORT = "armed"
    DISARMED_REPORT = "disarmed"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    RELOAD = "reload"
    REPAIR_CONFIRM = "repair_confirm"
    OPERATION_END = "operation_end"
    KEY_REFUSED = "key_refused"


@dataclass(frozen=True)
class ModeState:
    mode: ProgramMode = ProgramMode.CLOSED
    generation: str | None = None
    operation_id: str | None = None
    saw_627: bool = False
    revision: int = 0

    def stored(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "generation": self.generation,
            "operation_id": self.operation_id,
            "saw_627": self.saw_627,
            "revision": self.revision,
        }

    @classmethod
    def restore(cls, data: dict[str, object]) -> ModeState:
        mode = ProgramMode(str(data.get("mode", "doubt")))
        if mode is ProgramMode.OPEN:
            mode = ProgramMode.DOUBT
        return cls(
            mode=mode,
            generation=str(data.get("generation") or uuid4())
            if mode is not ProgramMode.CLOSED
            else None,
            saw_627=bool(data.get("saw_627", False)),
            revision=int(str(data.get("revision", 0))) + 1,
        )


def transition(
    state: ModeState,
    event: ModeEvent,
    *,
    operation_id: str | None = None,
    generation: str | None = None,
    entry_complete: bool = False,
    holding: bool = False,
    installer: bool = False,
    everyday: bool = False,
) -> ModeState:
    """Fold one event; rejected keys and stale confirmations raise ValueError."""
    next_revision = state.revision + 1
    if event is ModeEvent.OPERATION_START:
        if operation_id is None:
            raise ValueError("operation id required")
        if everyday:
            if state.mode is not ProgramMode.CLOSED:
                raise ValueError("Program Mode is not closed")
            return state
        if state.operation_id is not None and state.operation_id != operation_id:
            raise ValueError("another operation holds the keypad")
        if state.mode is not ProgramMode.CLOSED:
            if not installer:
                raise ValueError("Program Mode is not closed")
            return replace(state, operation_id=operation_id, revision=next_revision)
        return ModeState(
            ProgramMode.DOUBT, str(uuid4()), operation_id, False, next_revision
        )
    if event is ModeEvent.KEY_WRITE:
        if operation_id is None:
            if state.mode is not ProgramMode.CLOSED:
                raise ValueError("Program Mode is not closed")
        elif state.operation_id != operation_id:
            raise ValueError("this operation does not own Program Mode")
        elif not installer and state.mode is ProgramMode.OPEN and not entry_complete:
            raise ValueError("entry key after Program Mode opened")
        elif not installer and state.mode is ProgramMode.DOUBT and entry_complete:
            raise ValueError("menu key before this operation's 627")
        return state
    if event is ModeEvent.OPEN_REPORT:
        owner = state.operation_id if entry_complete else None
        return ModeState(
            ProgramMode.OPEN,
            state.generation or str(uuid4()),
            owner,
            True,
            next_revision,
        )
    if event is ModeEvent.CLOSE_REPORT:
        return ModeState(revision=next_revision)
    if event is ModeEvent.ARMED_REPORT:
        if (
            state.mode is ProgramMode.DOUBT
            and not state.saw_627
            and state.operation_id is None
            and not holding
        ):
            return ModeState(revision=next_revision)
        return state
    if event is ModeEvent.DISARMED_REPORT:
        return state
    if event in (ModeEvent.DISCONNECT, ModeEvent.RECONNECT, ModeEvent.RELOAD):
        if state.mode is ProgramMode.OPEN:
            return replace(
                state, mode=ProgramMode.DOUBT, saw_627=True, revision=next_revision
            )
        return replace(state, revision=next_revision)
    if event is ModeEvent.REPAIR_CONFIRM:
        if holding or state.operation_id is not None:
            raise ValueError("An operation is still using the keypad")
        if state.mode is ProgramMode.CLOSED or generation != state.generation:
            raise ValueError(
                "This repair is stale; open the current Program Mode repair"
            )
        return ModeState(revision=next_revision)
    if event is ModeEvent.OPERATION_END:
        if everyday:
            return state
        if state.operation_id != operation_id:
            if state.mode is ProgramMode.OPEN and state.operation_id is None:
                return replace(
                    state, mode=ProgramMode.DOUBT, saw_627=True, revision=next_revision
                )
            return state
        if state.mode is ProgramMode.OPEN:
            return replace(
                state,
                mode=ProgramMode.DOUBT,
                operation_id=None,
                saw_627=True,
                revision=next_revision,
            )
        return replace(state, operation_id=None, revision=next_revision)
    if event is ModeEvent.KEY_REFUSED:
        if (
            state.mode is ProgramMode.DOUBT
            and state.operation_id == operation_id
            and not holding
            and not state.saw_627
        ):
            return ModeState(revision=next_revision)
        return state
    raise ValueError(f"unknown event: {event}")
