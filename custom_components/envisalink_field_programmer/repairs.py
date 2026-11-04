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


class ProgramModeClosedFlow(ConfirmRepairFlow):
    """The user checks the keypad, leaves Program Mode with *99, and confirms."""

    def __init__(self, entry_id: str) -> None:
        super().__init__()
        self._entry_id = entry_id

    @override
    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> RepairsFlowResult:
        if user_input is not None:
            entry: VistaConsoleConfigEntry | None = (
                self.hass.config_entries.async_get_entry(self._entry_id)
            )
            if entry is not None and entry.state is ConfigEntryState.LOADED:
                entry.runtime_data.async_confirm_program_mode_closed()
        return await super().async_step_confirm(user_input)


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, str | int | float | None] | None
) -> RepairsFlow:
    """The confirm flow for this integration's one fixable issue."""
    if issue_id.startswith(f"{ISSUE_PROGRAM_MODE_UNKNOWN}_") and data:
        return ProgramModeClosedFlow(str(data["entry_id"]))
    raise ValueError(f"{DOMAIN} has no repair flow for {issue_id}")
