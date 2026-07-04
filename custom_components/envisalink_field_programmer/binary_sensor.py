"""Zone binary sensors and system/partition trouble sensors."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_ZONE_NAMES, DOMAIN
from .coordinator import VistaConsoleCoordinator
from .entity import VistaConsoleEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VistaConsoleCoordinator = hass.data[DOMAIN][entry.entry_id]
    zone_names: dict[str, str] = entry.options.get(
        CONF_ZONE_NAMES, entry.data.get(CONF_ZONE_NAMES, {})
    )
    entities: list[BinarySensorEntity] = [
        VistaZoneSensor(coordinator, number, zone_names.get(str(number)))
        for number in sorted(coordinator.data.zones)
    ]
    entities.append(VistaTroubleSensor(coordinator))
    async_add_entities(entities)


class VistaZoneSensor(VistaConsoleEntity, BinarySensorEntity):
    """Open/closed state of a single Vista zone."""

    _attr_device_class = BinarySensorDeviceClass.OPENING

    def __init__(
        self, coordinator: VistaConsoleCoordinator, zone_number: int, name: str | None
    ) -> None:
        super().__init__(coordinator, f"zone_{zone_number}")
        self._zone_number = zone_number
        self._attr_name = name or f"Zone {zone_number}"

    @property
    def _zone(self):
        return self.coordinator.data.zone(self._zone_number)

    @property
    def is_on(self) -> bool:
        return self._zone.open

    @property
    def extra_state_attributes(self) -> dict:
        zone = self._zone
        return {
            "zone_number": self._zone_number,
            "partition": zone.partition,
            "config_entry_id": self.coordinator.config_entry.entry_id,
            "alarm": zone.alarm,
            "tamper": zone.tamper,
            "fault": zone.fault,
            "bypassed": zone.bypassed,
        }


class VistaTroubleSensor(VistaConsoleEntity, BinarySensorEntity):
    """Aggregate system trouble condition (AC/battery/bell/FTC/tamper/fire)."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "system_trouble")
        self._attr_name = "System Trouble"

    @property
    def is_on(self) -> bool:
        system = self.coordinator.data.system
        return any(
            (
                system.ac_trouble,
                system.battery_trouble,
                system.bell_trouble,
                system.ftc_trouble,
                system.fire_trouble,
                system.general_tamper,
                system.installers_mode,
            )
        )

    @property
    def extra_state_attributes(self) -> dict:
        system = self.coordinator.data.system
        return {
            "ac_trouble": system.ac_trouble,
            "battery_trouble": system.battery_trouble,
            "bell_trouble": system.bell_trouble,
            "ftc_trouble": system.ftc_trouble,
            "fire_trouble": system.fire_trouble,
            "general_tamper": system.general_tamper,
            "installers_mode": system.installers_mode,
        }
