"""Zone bypass switches, and the programming form's on/off fields.

Bypassing a zone through the keypad (``*1`` + zone number + ``#``) is an
ordinary, documented end-user operation on Vista panels -- unlike field
programming, it requires no installer code and carries no risk of a
lockout. It still goes through the same keystroke guard as everything else
(see programming.py) for defense in depth.

The other switches here send nothing at all. They are the boolean fields of
the guided operations: whether a programmed zone reports to the monitoring
station, and the three confirmations. A confirmation is spent by the button
that used it -- every press turns all three off again -- so leaving one on
cannot authorize a second write nobody meant.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import ProgrammingEntity, VistaConsoleEntity
from .panels import GuidedOp, Verification

# Reads are push-driven, but a bypass writes a keystroke sequence to the panel
# and the client's lock is held per frame, not per sequence. One at a time, so
# two bypasses cannot interleave their keypresses.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = [
        VistaZoneBypassSwitch(coordinator, number) for number in sorted(coordinator.data.zones)
    ]
    supported = coordinator.dialect.supported_guided_ops
    if supported:
        entities.append(
            ProgrammingSwitch(
                coordinator,
                suffix="program_confirm",
                translation_key="confirm_programming",
                attribute="confirm",
            )
        )
        # Nothing to acknowledge on the one model built from its own guide.
        if coordinator.panel_model.verification is not Verification.VERIFIED:
            entities.append(
                ProgrammingSwitch(
                    coordinator,
                    suffix="program_confirm_unverified_model",
                    translation_key="confirm_unverified_model",
                    attribute="confirm_unverified_model",
                )
            )
    if GuidedOp.ZONE in supported:
        entities += [
            ProgrammingSwitch(
                coordinator,
                suffix="program_zone_report_enabled",
                translation_key="zone_report_enabled",
                attribute="zone_report_enabled",
            ),
            ProgrammingSwitch(
                coordinator,
                suffix="program_confirm_life_safety",
                translation_key="confirm_life_safety",
                attribute="confirm_life_safety",
            ),
        ]
    async_add_entities(entities)


class VistaZoneBypassSwitch(VistaConsoleEntity, SwitchEntity):
    """Bypass/un-bypass a single zone."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "zone_bypass"

    def __init__(self, coordinator: VistaConsoleCoordinator, zone_number: int) -> None:
        super().__init__(coordinator, f"zone_{zone_number}_bypass")
        self._zone_number = zone_number
        self._attr_translation_placeholders = {"number": str(zone_number)}

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.zone(self._zone_number).bypassed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "zone_number": self._zone_number,
            "config_entry_id": self.coordinator.entry.entry_id,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        if not self.is_on:
            await self.coordinator.async_toggle_zone_bypass(self._zone_number)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if self.is_on:
            await self.coordinator.async_toggle_zone_bypass(self._zone_number)


class ProgrammingSwitch(ProgrammingEntity, SwitchEntity):
    """One on/off field of the programming form. Sends nothing to the panel."""

    _attr_device_class = SwitchDeviceClass.SWITCH

    def __init__(
        self,
        coordinator: VistaConsoleCoordinator,
        *,
        suffix: str,
        translation_key: str,
        attribute: str,
    ) -> None:
        super().__init__(coordinator, suffix)
        self._attr_translation_key = translation_key
        self._attribute = attribute

    @property
    def is_on(self) -> bool:
        return bool(getattr(self.form, self._attribute))

    async def async_turn_on(self, **kwargs: Any) -> None:
        setattr(self.form, self._attribute, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        setattr(self.form, self._attribute, False)
        self.async_write_ha_state()
