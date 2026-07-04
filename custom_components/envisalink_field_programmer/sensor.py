"""Diagnostic sensors: last raw TPI event and per-partition last user."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VistaConsoleCoordinator
from .entity import VistaConsoleEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VistaConsoleCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [VistaLastEventSensor(coordinator)]
    entities.extend(
        VistaLastUserSensor(coordinator, number)
        for number in sorted(coordinator.data.partitions)
    )
    async_add_entities(entities)


class VistaLastEventSensor(VistaConsoleEntity, SensorEntity):
    """The most recently received raw TPI event, for diagnostics."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "last_event")
        self._attr_name = "Last Event"

    @property
    def native_value(self) -> str | None:
        event = self.coordinator.last_event
        return event.name if event else None

    @property
    def extra_state_attributes(self) -> dict:
        event = self.coordinator.last_event
        if event is None:
            return {}
        return {"code": event.code, "raw_data": event.raw_data, "fields": event.fields}


class VistaLastUserSensor(VistaConsoleEntity, SensorEntity):
    """Last user code number that armed/disarmed a partition."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: VistaConsoleCoordinator, partition_number: int) -> None:
        super().__init__(coordinator, f"partition_{partition_number}_last_user")
        self._partition_number = partition_number
        self._attr_name = (
            "Last User"
            if len(coordinator.data.partitions) == 1
            else f"Partition {partition_number} Last User"
        )

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.partition(self._partition_number).last_user
