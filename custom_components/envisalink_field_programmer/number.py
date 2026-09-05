"""The programming form's numeric fields, as numbers on the panel device.

Which zone to program, and what value a timing field should take. Setting one
writes to the entry's programming form and nothing else; the panel hears
nothing until a button in button.py is pressed with the confirm switch on.

The bounds here are the widest a value can be. What a *particular* timing field
accepts is narrower and dialect-specific (residential seconds with extended-time
codes, commercial units of 15 seconds), so the real range check stays in the
dialect's keystroke builder, where the chosen field is known, and a value it
refuses comes back as a translated error on the button.
"""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import ProgrammingEntity
from .panels import GuidedOp

# Nothing here reaches the panel; setting a value only writes to the form.
PARALLEL_UPDATES = 0

# The *56 zone menu addresses zones 1-64, whatever the panel's own maximum is.
ZONE_MENU_MAX_ZONE = 64
# Wide enough for every timing encoding: residential entry delay 2 tops out at
# the 99 extended-time code, commercial at 15 units of 15 seconds.
TIMING_VALUE_MAX = 99


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    supported = coordinator.dialect.supported_guided_ops
    entities: list[NumberEntity] = []

    if GuidedOp.ZONE in supported:
        entities.append(
            ProgrammingNumber(
                coordinator,
                suffix="program_zone_number",
                translation_key="zone_number",
                minimum=1,
                maximum=min(ZONE_MENU_MAX_ZONE, coordinator.panel_model.max_zones),
                attribute="zone_number",
            )
        )
    if GuidedOp.TIMING in supported:
        entities.append(
            ProgrammingNumber(
                coordinator,
                suffix="program_timing_value",
                translation_key="timing_value",
                minimum=0,
                maximum=TIMING_VALUE_MAX,
                attribute="timing_value",
            )
        )

    async_add_entities(entities)


class ProgrammingNumber(ProgrammingEntity, NumberEntity):
    """One numeric field of the programming form."""

    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(
        self,
        coordinator: VistaConsoleCoordinator,
        *,
        suffix: str,
        translation_key: str,
        minimum: int,
        maximum: int,
        attribute: str,
    ) -> None:
        super().__init__(coordinator, suffix)
        self._attr_translation_key = translation_key
        self._attr_native_min_value = float(minimum)
        self._attr_native_max_value = float(maximum)
        self._attribute = attribute

    @property
    def native_value(self) -> float | None:
        current: int | None = getattr(self.form, self._attribute)
        return None if current is None else float(current)

    async def async_set_native_value(self, value: float) -> None:
        setattr(self.form, self._attribute, int(value))
        self.async_write_ha_state()
