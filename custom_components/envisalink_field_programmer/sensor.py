"""Diagnostic sensors: last raw TPI event, per-partition last user, and what
became of the last programming button press."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import VistaConsoleEntity
from .field_programming import ProgrammingOutcome

# Push-driven; the coordinator delivers every update.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [VistaLastEventSensor(coordinator)]
    entities.extend(
        VistaLastUserSensor(coordinator, number) for number in sorted(coordinator.data.partitions)
    )
    # Only where there is a programming button that could produce a result.
    if coordinator.dialect.supported_guided_ops:
        entities.append(VistaLastProgrammingResultSensor(coordinator))
    async_add_entities(entities)


class VistaLastEventSensor(VistaConsoleEntity, SensorEntity):
    """The most recently received raw TPI event, for diagnostics.

    Disabled by default: it changes on every keepalive acknowledgement, which
    is a state write every 30 seconds for a value only useful while debugging
    the protocol. Enable it in the entity settings when that is what you want.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "last_event"

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "last_event")

    @property
    def native_value(self) -> str | None:
        event = self.coordinator.last_event
        return event.name if event else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
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
        # One partition needs no number in the name; several do.
        if len(coordinator.data.partitions) == 1:
            self._attr_translation_key = "last_user"
        else:
            self._attr_translation_key = "partition_last_user"
            self._attr_translation_placeholders = {"number": str(partition_number)}

    @property
    def native_value(self) -> str | None:
        return self.coordinator.data.partition(self._partition_number).last_user


class VistaLastProgrammingResultSensor(VistaConsoleEntity, SensorEntity):
    """What became of the last press of a programming button.

    The state is the outcome; the reply that decided it is an attribute. Note
    what "success" can and cannot mean here: the Envisalink acknowledged every
    keystroke of the sequence, which is as far as this protocol sees. Nothing
    can read the panel's programming back, so the panel's own opinion of what
    it stored is still only visible at the keypad.
    """

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_options = [outcome.value for outcome in ProgrammingOutcome]
    _attr_translation_key = "last_programming_result"

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "last_programming_result")

    @property
    def native_value(self) -> str | None:
        result = self.coordinator.last_programming_result
        return result.outcome.value if result else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self.coordinator.last_programming_result
        if result is None:
            return {}
        return {"action": result.action, "detail": result.detail}
