"""Zone bypass switches.

Bypassing a zone through the keypad (``*1`` + zone number + ``#``) is an
ordinary, documented end-user operation on Vista panels -- unlike field
programming, it requires no installer code and carries no risk of a
lockout. It still goes through the same keystroke guard as everything else
(see programming.py) for defense in depth.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import VistaConsoleEntity

# Push-driven; the coordinator delivers every update.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        VistaZoneBypassSwitch(coordinator, number) for number in sorted(coordinator.data.zones)
    )


class VistaZoneBypassSwitch(VistaConsoleEntity, SwitchEntity):
    """Bypass/un-bypass a single zone."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: VistaConsoleCoordinator, zone_number: int) -> None:
        super().__init__(coordinator, f"zone_{zone_number}_bypass")
        self._zone_number = zone_number
        self._attr_name = f"Zone {zone_number} Bypass"

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.zone(self._zone_number).bypassed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "zone_number": self._zone_number,
            "config_entry_id": self.coordinator.config_entry.entry_id,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.is_on:
            await self.coordinator.async_toggle_zone_bypass(self._zone_number)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self.coordinator.async_toggle_zone_bypass(self._zone_number)
