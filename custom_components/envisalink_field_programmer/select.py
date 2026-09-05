"""The programming form's enumerated fields, as selects on the panel device.

Zone type, the three partition pickers, wiring style, response time, which
timing field to edit, which function key and what it should do: every field of
the guided actions whose values are a fixed list. Selecting an option writes
that value into the entry's programming form and nothing else -- the panel
hears nothing until a button in button.py is pressed with the confirm switch
on.

Options are slugs rather than raw Vista codes so each one carries a translated
name (a "Zone type" of ``09`` means nothing on a dashboard). The slug tables
here are the only place the two representations meet.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import ProgrammingEntity
from .field_programming import (
    FUNCTION_KEY_ACTION_LABELS,
    FunctionKeyAction,
    FunctionKeyLetter,
    HardwireType,
    ResponseTime,
)
from .panels import GuidedOp

# Nothing here reaches the panel; a selection only writes to the form.
PARALLEL_UPDATES = 0

# The *56 and *57 menus both take a partition of 1-3, whatever the panel's own
# maximum is; the commercial timing fields are selected per partition 1-8.
ZONE_MENU_MAX_PARTITION = 3
TIMING_MAX_PARTITION = 8

_HARDWIRE_TYPE_OPTIONS: dict[str, HardwireType] = {
    "end_of_line": HardwireType.END_OF_LINE,
    "normally_closed": HardwireType.NORMALLY_CLOSED,
    "normally_open": HardwireType.NORMALLY_OPEN,
    "zone_doubling": HardwireType.ZONE_DOUBLING,
    "double_balanced": HardwireType.DOUBLE_BALANCED,
}

_RESPONSE_TIME_OPTIONS: dict[str, ResponseTime] = {
    "ms_10": ResponseTime.MS_10,
    "ms_350": ResponseTime.MS_350,
    "ms_700": ResponseTime.MS_700,
    "sec_1_2": ResponseTime.SEC_1_2,
}

_FUNCTION_KEY_OPTIONS: dict[str, FunctionKeyLetter] = {
    f"key_{letter.value.lower()}": letter for letter in FunctionKeyLetter
}

_FUNCTION_KEY_ACTION_OPTIONS: dict[str, FunctionKeyAction] = {
    action.name.lower(): action for action in FUNCTION_KEY_ACTION_LABELS
}


def _partition_options(maximum: int) -> dict[str, int]:
    return {f"partition_{number}": number for number in range(1, maximum + 1)}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    supported = coordinator.dialect.supported_guided_ops
    entities: list[SelectEntity] = []

    if GuidedOp.ZONE in supported:
        # The zone-type options come from the dialect's own table, so a model
        # whose codes differ offers its own list rather than the residential
        # one. The slug is the code, which is what keeps the names translatable
        # without a table per dialect.
        zone_types = {f"type_{code:02d}": code for code in sorted(coordinator.dialect.zone_types())}
        partitions = _partition_options(
            min(ZONE_MENU_MAX_PARTITION, coordinator.panel_model.max_partitions)
        )
        entities += [
            ProgrammingSelect(
                coordinator,
                suffix="program_zone_type",
                translation_key="zone_type",
                options=zone_types,
                attribute="zone_type",
            ),
            ProgrammingSelect(
                coordinator,
                suffix="program_zone_partition",
                translation_key="zone_partition",
                options=partitions,
                attribute="zone_partition",
            ),
            ProgrammingSelect(
                coordinator,
                suffix="program_zone_hardwire_type",
                translation_key="zone_hardwire_type",
                options=_HARDWIRE_TYPE_OPTIONS,
                attribute="zone_hardwire_type",
            ),
            ProgrammingSelect(
                coordinator,
                suffix="program_zone_response_time",
                translation_key="zone_response_time",
                options=_RESPONSE_TIME_OPTIONS,
                attribute="zone_response_time",
            ),
        ]

    if GuidedOp.TIMING in supported:
        timing_fields = {f"field_{key}": key for key in sorted(coordinator.dialect.timing_fields())}
        entities.append(
            ProgrammingSelect(
                coordinator,
                suffix="program_timing_field",
                translation_key="timing_field",
                options=timing_fields,
                attribute="timing_field",
            )
        )
        # Only the commercial dialect scopes a timing edit to a partition, so
        # the picker is offered only where it changes what is sent.
        if any(f.partition_specific for f in coordinator.dialect.timing_fields().values()):
            entities.append(
                ProgrammingSelect(
                    coordinator,
                    suffix="program_timing_partition",
                    translation_key="timing_partition",
                    options=_partition_options(
                        min(TIMING_MAX_PARTITION, coordinator.panel_model.max_partitions)
                    ),
                    attribute="timing_partition",
                )
            )

    if GuidedOp.FUNCTION_KEY in supported:
        entities += [
            ProgrammingSelect(
                coordinator,
                suffix="program_function_key_letter",
                translation_key="function_key",
                options=_FUNCTION_KEY_OPTIONS,
                attribute="function_key",
            ),
            ProgrammingSelect(
                coordinator,
                suffix="program_function_key_action",
                translation_key="function_key_action",
                options=_FUNCTION_KEY_ACTION_OPTIONS,
                attribute="function_key_action",
            ),
            ProgrammingSelect(
                coordinator,
                suffix="program_function_key_partition",
                translation_key="function_key_partition",
                options=_partition_options(
                    min(ZONE_MENU_MAX_PARTITION, coordinator.panel_model.max_partitions)
                ),
                attribute="function_key_partition",
            ),
        ]

    async_add_entities(entities)


class ProgrammingSelect(ProgrammingEntity, SelectEntity):
    """One enumerated field of the programming form.

    The slug table is the entity's options; the values behind it are what the
    guided operations take. An unset field has no current option, which is what
    a button press reports as a missing value rather than guessing a default.
    """

    def __init__(
        self,
        coordinator: VistaConsoleCoordinator,
        *,
        suffix: str,
        translation_key: str,
        options: Mapping[str, Any],
        attribute: str,
    ) -> None:
        super().__init__(coordinator, suffix)
        self._attr_translation_key = translation_key
        self._attr_options = list(options)
        self._values = dict(options)
        self._attribute = attribute

    @property
    def current_option(self) -> str | None:
        # No option holds None, so an unset field falls out of this as None.
        current = getattr(self.form, self._attribute)
        return next((option for option, value in self._values.items() if value == current), None)

    async def async_select_option(self, option: str) -> None:
        setattr(self.form, self._attribute, self._values[option])
        self.async_write_ha_state()
