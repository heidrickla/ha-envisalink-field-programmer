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
            "bypassed": zone.bypassed,
            "seconds_since_fault": zone.seconds_since_fault,
        }


class VistaTroubleSensor(VistaConsoleEntity, BinarySensorEntity):
    """Aggregate trouble condition across all partitions (AC/battery/system trouble).

    The real protocol only reports these as per-partition icon-LED flags
    (see state_machine.py), not as distinct system-wide trouble types the
    way the earlier, incorrect protocol implementation assumed -- so this
    aggregates across every configured partition instead of tracking
    separate AC/battery/bell/FTC/tamper conditions.
    """

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "system_trouble")
        self._attr_name = "System Trouble"

    @property
    def is_on(self) -> bool:
        if self.coordinator.data.system.installers_mode:
            return True
        return any(
            partition.trouble or partition.low_battery or not partition.ac_present
            for partition in self.coordinator.data.partitions.values()
        )

    @property
    def extra_state_attributes(self) -> dict:
        system = self.coordinator.data.system
        return {
            "installers_mode": system.installers_mode,
            "partitions": {
                number: {
                    "trouble": partition.trouble,
                    "low_battery": partition.low_battery,
                    "ac_present": partition.ac_present,
                }
                for number, partition in self.coordinator.data.partitions.items()
            },
        }
