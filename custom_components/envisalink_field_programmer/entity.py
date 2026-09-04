"""Shared base entity for Envisalink Field Programmer platforms."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VistaConsoleCoordinator


class VistaConsoleEntity(CoordinatorEntity[VistaConsoleCoordinator]):
    """Base entity wiring shared device info back to the panel/EVL."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VistaConsoleCoordinator, unique_id_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_id_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.entry
        return DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Honeywell / EyezOn",
            model="VISTA panel via Envisalink EVL-3/EVL-4",
        )

    @property
    def available(self) -> bool:
        return bool(super().available and self.coordinator.data.system.connected)
