"""Repair flow for a Program Mode the panel never reported closed."""

from __future__ import annotations

from typing import override

from homeassistant.components.repairs import (
    ConfirmRepairFlow,
    RepairsFlow,
    RepairsFlowResult,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import DOMAIN, ISSUE_PROGRAM_MODE_UNKNOWN
from .coordinator import VistaConsoleConfigEntry
from .program_mode_state import ModeRefusal, Refusal

# What the flow tells the user for each reason the state refused the confirm.
_ABORT_REASONS = {
    Refusal.HELD: "operation_in_progress",
    Refusal.SETTLED: "already_settled",
    Refusal.STALE: "stale_repair",
}


class ProgramModeClosedFlow(ConfirmRepairFlow):
    """The user checks the keypad, leaves Program Mode with *99, and confirms."""

    def __init__(self, entry_id: str, generation: str, revision: int) -> None:
        super().__init__()
        self._entry_id = entry_id
        self._generation = generation
        self._revision = revision

    @override
    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        if user_input is not None:
            entry: VistaConsoleConfigEntry | None = (
                self.hass.config_entries.async_get_entry(self._entry_id)
            )
            if entry is None or entry.state is not ConfigEntryState.LOADED:
                return self.async_abort(reason="entry_not_loaded")
            try:
                await entry.runtime_data.async_confirm_program_mode_closed(
                    self._generation, self._revision
                )
            except ModeRefusal as err:
                return self.async_abort(
                    reason=_ABORT_REASONS.get(err.reason, "stale_repair")
                )
        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    """The confirm flow for this integration's one fixable issue."""
    if issue_id.startswith(f"{ISSUE_PROGRAM_MODE_UNKNOWN}_") and data:
        # An issue saved by 0.8.0 has no revision; -1 matches no state, so its
        # flow is stale and the current issue carries the revision.
        revision = data.get("revision")
        return ProgramModeClosedFlow(
            str(data["entry_id"]),
            str(data["generation"]),
            int(revision) if revision is not None else -1,
        )
    raise ValueError(f"{DOMAIN} has no repair flow for {issue_id}")
