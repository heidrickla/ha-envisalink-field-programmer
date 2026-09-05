"""The three programming buttons on the panel device.

A button is the only thing on the device page that reaches the panel. It reads
whatever the config entities currently hold and runs the matching guided
operation from field_programming_services.py -- the same coroutine the action
of the same name runs, so every guard applies identically whether a person
pressed the button or an automation called the action.

Two conditions are checked here and only here, because they exist only on the
device page: the confirm switch has to be on, and every value the operation
needs has to be set. Both refusals are ServiceValidationErrors, so Home
Assistant shows the sentence without a traceback.

Every press that got past the confirm switch spends it: all three confirmations
go off again afterwards, whether the panel accepted the sequence, refused it,
or was never reached. The result sensor then says which of those happened.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, RESPONSE_ACCEPTED, TPI_RESPONSE_CODES
from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .entity import ProgrammingEntity
from .field_programming import (
    ProgrammingForm,
    ProgrammingOutcome,
    ProgrammingResult,
)
from .field_programming_services import (
    async_program_function_key,
    async_program_zone,
    async_set_system_timing,
)
from .panels import GuidedOp

_LOGGER = logging.getLogger(__name__)

# A press writes a whole keystroke sequence to a panel that takes one command
# at a time, and the client's lock is held per frame rather than per sequence.
# One at a time, so two presses cannot interleave their keypresses.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VistaConsoleConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    supported = coordinator.dialect.supported_guided_ops
    entities: list[ButtonEntity] = []
    if GuidedOp.ZONE in supported:
        entities.append(ProgramZoneButton(coordinator))
    if GuidedOp.TIMING in supported:
        entities.append(SetSystemTimingButton(coordinator))
    if GuidedOp.FUNCTION_KEY in supported:
        entities.append(ProgramFunctionKeyButton(coordinator))
    async_add_entities(entities)


class ProgrammingButton(ProgrammingEntity, ButtonEntity):
    """Submit the current form values as one guided programming operation."""

    # The plain-language name of this button, for the "set X first" refusal.
    action_name: str
    # The action this button shares its guards with, recorded on the result.
    action_id: str

    async def _async_program(self, form: ProgrammingForm) -> None:
        """Run the operation. Subclasses read the values they need."""
        raise NotImplementedError

    def _require[T](self, value: T | None, field: str) -> T:
        """The value, or a refusal naming the field the press is missing."""
        if value is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="programming_value_unset",
                translation_placeholders={"field": field, "action": self.action_name},
            )
        return value

    def _record(self, outcome: ProgrammingOutcome, detail: str) -> None:
        self.coordinator.last_programming_result = ProgrammingResult(
            action=self.action_id, outcome=outcome, detail=detail
        )

    async def async_press(self) -> None:
        form = self.form
        if not form.confirm:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="confirm_switch_off",
                translation_placeholders={"action": self.action_name},
            )
        try:
            await self._async_program(form)
        except ServiceValidationError as err:
            # A guard said no and nothing was sent.
            self._record(ProgrammingOutcome.REFUSED, str(err))
            raise
        except HomeAssistantError as err:
            # The sequence was sent and something rejected or dropped it, so
            # what reached the panel is unknown. Say so rather than guessing.
            _LOGGER.warning("%s did not complete: %s", self.action_name, err)
            self._record(ProgrammingOutcome.FAILED, str(err))
            raise
        else:
            self._record(ProgrammingOutcome.SUCCESS, TPI_RESPONSE_CODES[RESPONSE_ACCEPTED])
        finally:
            # An authorization is spent on exactly one attempt, however it went.
            form.clear_confirmations()
            self.coordinator.async_update_listeners()


class ProgramZoneButton(ProgrammingButton):
    """Send the *56 zone settings the form holds."""

    _attr_translation_key = "program_zone"
    action_name = "Program zone"
    action_id = "program_zone"

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "program_zone")

    async def _async_program(self, form: ProgrammingForm) -> None:
        zone_number = self._require(form.zone_number, "the zone to program")
        zone_type = self._require(form.zone_type, "the zone type")
        partition = self._require(form.zone_partition, "the zone partition")
        await async_program_zone(
            self.coordinator,
            zone_number=zone_number,
            zone_type=zone_type,
            partition=partition,
            report_enabled=form.zone_report_enabled,
            hardwire_type=form.zone_hardwire_type,
            response_time=form.zone_response_time,
            confirm_life_safety=form.confirm_life_safety,
            confirm_unverified_model=form.confirm_unverified_model,
        )


class SetSystemTimingButton(ProgrammingButton):
    """Send the timing field and value the form holds."""

    _attr_translation_key = "set_system_timing"
    action_name = "Set system timing"
    action_id = "set_system_timing"

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "set_system_timing")

    async def _async_program(self, form: ProgrammingForm) -> None:
        field = self._require(form.timing_field, "the timing field")
        value = self._require(form.timing_value, "the timing value")
        await async_set_system_timing(
            self.coordinator,
            field=field,
            value=value,
            partition=form.timing_partition,
            confirm_unverified_model=form.confirm_unverified_model,
        )


class ProgramFunctionKeyButton(ProgrammingButton):
    """Send the *57 function-key assignment the form holds."""

    _attr_translation_key = "program_function_key"
    action_name = "Program function key"
    action_id = "program_function_key"

    def __init__(self, coordinator: VistaConsoleCoordinator) -> None:
        super().__init__(coordinator, "program_function_key")

    async def _async_program(self, form: ProgrammingForm) -> None:
        key = self._require(form.function_key, "the function key")
        action = self._require(form.function_key_action, "the function key action")
        partition = self._require(form.function_key_partition, "the function key partition")
        await async_program_function_key(
            self.coordinator,
            key=key,
            partition=partition,
            action=action,
            confirm_unverified_model=form.confirm_unverified_model,
        )
