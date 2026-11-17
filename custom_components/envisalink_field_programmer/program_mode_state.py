"""The single transition function for panel Program Mode evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4

from .models import ProgramMode


class ModeEvent(Enum):
    OPERATION_START = "operation_start"
    KEY_WRITE = "key_write"
    NO_KEY_SENT = "no_key_sent"
    OPEN_REPORT = "627"
    CLOSE_REPORT = "628"
    ARMED_REPORT = "armed"
    DISARMED_REPORT = "disarmed"
    DISCONNECT = "disconnect"
    RECONNECT = "reconnect"
    RELOAD = "reload"
    REPAIR_CONFIRM = "repair_confirm"
    OPERATION_END = "operation_end"


class Refusal(Enum):
    """Why an event was refused; a caller picks its message from this."""

    NOT_CLOSED = "not_closed"
    HELD = "held"
    NOT_OWNER = "not_owner"
    ENTRY_AFTER_OPEN = "entry_after_open"
    MENU_BEFORE_OPEN = "menu_before_open"
    SETTLED = "settled"
    STALE = "stale"
    STORAGE_FAILED = "storage_failed"


class ModeRefusal(ValueError):
    """A key or confirmation the table refuses."""

    def __init__(self, reason: Refusal) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass(frozen=True)
class Holder:
    """What the keypad's holder has sent, as far as it bears on who owns a 627."""

    operation_id: str
    installer: bool
    # A guided operation's entry and acknowledged key count.
    entry_length: int = 0
    written: int = 0


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


def explains_open_report(state: ModeState, holder: Holder | None) -> bool:
    """Whether the holder's own keys account for a 627 that just arrived.

    A guided operation explains only the first 627 after its own doubt, once
    its entry is acknowledged. An installer operation explains a 627 only
    after an acknowledged key, since a confirmed send may type anything.
    """
    if holder is None or state.operation_id != holder.operation_id:
        return False
    if holder.installer:
        return holder.written > 0
    return (
        state.mode is ProgramMode.DOUBT
        and holder.entry_length > 0
        and holder.written >= holder.entry_length
    )


def transition(
    state: ModeState,
    event: ModeEvent,
    *,
    operation_id: str | None = None,
    generation: str | None = None,
    revision: int | None = None,
    entry_complete: bool = False,
    holding: bool = False,
    installer: bool = False,
    everyday: bool = False,
    holder: Holder | None = None,
) -> ModeState:
    """Fold one event; rejected keys and stale confirmations raise ModeRefusal."""
    next_revision = state.revision + 1
    if event is ModeEvent.OPERATION_START:
        if operation_id is None:
            raise ValueError("operation id required")
        if everyday:
            if state.mode is not ProgramMode.CLOSED:
                raise ModeRefusal(Refusal.NOT_CLOSED)
            return state
        if state.operation_id is not None and state.operation_id != operation_id:
            raise ModeRefusal(Refusal.HELD)
        if state.mode is not ProgramMode.CLOSED:
            if not installer:
                raise ModeRefusal(Refusal.NOT_CLOSED)
            return replace(state, operation_id=operation_id, revision=next_revision)
        return ModeState(
            ProgramMode.DOUBT, str(uuid4()), operation_id, False, next_revision
        )
    if event is ModeEvent.KEY_WRITE:
        if operation_id is None:
            if state.mode is not ProgramMode.CLOSED:
                raise ModeRefusal(Refusal.NOT_CLOSED)
        elif state.operation_id != operation_id:
            raise ModeRefusal(Refusal.NOT_OWNER)
        elif not installer and state.mode is ProgramMode.OPEN and not entry_complete:
            raise ModeRefusal(Refusal.ENTRY_AFTER_OPEN)
        elif not installer and state.mode is ProgramMode.DOUBT and entry_complete:
            raise ModeRefusal(Refusal.MENU_BEFORE_OPEN)
        return state
    if event is ModeEvent.NO_KEY_SENT:
        if (
            state.mode is ProgramMode.DOUBT
            and operation_id is not None
            and state.operation_id == operation_id
            and state.generation == generation
            and not state.saw_627
        ):
            return ModeState(revision=next_revision)
        return state
    if event is ModeEvent.OPEN_REPORT:
        owner = state.operation_id if explains_open_report(state, holder) else None
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
            raise ModeRefusal(Refusal.HELD)
        if state.mode is ProgramMode.CLOSED:
            raise ModeRefusal(Refusal.SETTLED)
        if generation != state.generation or revision != state.revision:
            raise ModeRefusal(Refusal.STALE)
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
    raise ValueError(f"unknown event: {event}")
