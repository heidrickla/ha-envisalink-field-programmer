"""Alarm control panel entities, one per Vista partition."""
from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    CodeFormat,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    STATE_ALARM_ARMING,
    STATE_ALARM_DISARMED,
    STATE_ALARM_PENDING,
    STATE_ALARM_TRIGGERED,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_USER_CODE, DOMAIN
from .coordinator import VistaConsoleCoordinator
from .entity import VistaConsoleEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: VistaConsoleCoordinator = hass.data[DOMAIN][entry.entry_id]
    default_code = entry.options.get(CONF_USER_CODE, entry.data.get(CONF_USER_CODE, ""))
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
        self._attr_code_arm_required = False
        self._attr_code_format = CodeFormat.NUMBER if default_code == "" else None

    @property
    def _partition(self):
        return self.coordinator.data.partition(self._partition_number)

    @property
    def alarm_state(self) -> str | None:
        partition = self._partition
        if partition.alarm:
            return STATE_ALARM_TRIGGERED
        if partition.entry_delay:
            return STATE_ALARM_PENDING
        if partition.exit_delay:
            return STATE_ALARM_ARMING
        if partition.armed:
            return partition.arm_state
        return STATE_ALARM_DISARMED

    @property
    def extra_state_attributes(self) -> dict:
        partition = self._partition
        return {
            "partition_number": self._partition_number,
            "config_entry_id": self.coordinator.config_entry.entry_id,
            "ready": partition.ready,
            "force_arm_enabled": partition.force_arm_enabled,
            "chime_enabled": partition.chime_enabled,
            "trouble": partition.trouble,
            "busy": partition.busy,
            "keypad_lockout": partition.keypad_lockout,
            "failed_to_arm": partition.failed_to_arm,
            "last_user": partition.last_user,
        }

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self.coordinator.async_arm_away(self._partition_number)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self.coordinator.async_arm_stay(self._partition_number)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self.coordinator.async_arm_night(self._partition_number)

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        use_code = code or self._default_code
        if not use_code:
            raise HomeAssistantError(
                "No disarm code provided and no default user code configured for"
                " this integration's entry."
            )
        await self.coordinator.async_disarm(self._partition_number, use_code)
