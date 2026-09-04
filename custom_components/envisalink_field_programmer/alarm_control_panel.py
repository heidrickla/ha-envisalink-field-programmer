"""Alarm control panel entities, one per Vista partition."""

from __future__ import annotations

from typing import Any

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
    CodeFormat,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_USER_CODE, DOMAIN
from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import VistaConsoleEntity
from .models import PartitionState

# Push-driven; the coordinator delivers every update.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    default_code: str = entry.options.get(CONF_USER_CODE, entry.data.get(CONF_USER_CODE, ""))
    async_add_entities(
        VistaPartitionAlarmPanel(coordinator, number, default_code)
        for number in sorted(coordinator.data.partitions)
    )


class VistaPartitionAlarmPanel(VistaConsoleEntity, AlarmControlPanelEntity):
    """Represents one Vista partition as an HA alarm control panel."""

    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    def __init__(
        self, coordinator: VistaConsoleCoordinator, partition_number: int, default_code: str
    ) -> None:
        super().__init__(coordinator, f"partition_{partition_number}")
        self._partition_number = partition_number
        self._default_code = default_code
        self._attr_name = (
            "Partition"
            if len(coordinator.data.partitions) == 1
            else f"Partition {partition_number}"
        )
        # A real Vista panel arms/disarms by typing the user code followed
        # by a mode digit -- there is no code-free arm command over this
        # protocol, unlike some other panel families. So a code is always
        # required, sourced from either the service call or this entry's
        # configured default user code.
        self._attr_code_arm_required = default_code == ""
        self._attr_code_format = CodeFormat.NUMBER if default_code == "" else None

    @property
    def _partition(self) -> PartitionState:
        return self.coordinator.data.partition(self._partition_number)

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        # Note: there is no "pending" (entry delay) state here -- this
        # protocol's alpha-text parsing for entry delay isn't reliable
        # enough to port (see state_machine.py's module docstring; even the
        # reference `pyenvisalink` implementation leaves it unhandled).
        partition = self._partition
        if partition.alarm:
            return AlarmControlPanelState.TRIGGERED
        if partition.exit_delay:
            return AlarmControlPanelState.ARMING
        if partition.armed:
            return AlarmControlPanelState(partition.arm_state)
        return AlarmControlPanelState.DISARMED

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        partition = self._partition
        return {
            "partition_number": self._partition_number,
            "config_entry_id": self.coordinator.config_entry.entry_id,
            "ready": partition.ready,
            "chime_enabled": partition.chime_enabled,
            "trouble": partition.trouble,
            "ac_present": partition.ac_present,
            "low_battery": partition.low_battery,
            "bypass_active": partition.bypass_active,
            "last_user": partition.last_user,
        }

    def _require_code(self, code: str | None) -> str:
        use_code = code or self._default_code
        if not use_code:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_code",
            )
        return use_code

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self.coordinator.async_arm_away(self._partition_number, self._require_code(code))

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self.coordinator.async_arm_stay(self._partition_number, self._require_code(code))

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self.coordinator.async_arm_night(self._partition_number, self._require_code(code))

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self.coordinator.async_disarm(self._partition_number, self._require_code(code))
