"""HA services for the guided field-programming layer.

Every service here always opens Program Mode (installer code + 800), so
unlike the general-purpose ``send_keystrokes`` service, there is no "safe by
default" path -- ``confirm`` is required and must be true on every call.
Setting a zone to (or off of) a fire/CO zone type additionally requires
``confirm_life_safety``, since the TPI protocol cannot read back a zone's
*current* type before overwriting it (see field_programming.py).
"""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .field_programming import (
    LIFE_SAFETY_ZONE_TYPE_CODES,
    ZONE_TYPES,
    FunctionKeyAction,
    FunctionKeyLetter,
    HardwireType,
    ResponseTime,
    SystemTimingField,
    ZoneProgram,
    build_function_key_keystrokes,
    build_program_mode_wrapper,
    build_system_timing_keystrokes,
    build_zone_program_keystrokes,
)
from .programming import KeystrokeGuardError, validate_keystrokes

_LOGGER = logging.getLogger(__name__)

SERVICE_PROGRAM_ZONE = "program_zone"
SERVICE_SET_SYSTEM_TIMING = "set_system_timing"
SERVICE_PROGRAM_FUNCTION_KEY = "program_function_key"

ATTR_ENTRY_ID = "entry_id"
ATTR_CONFIRM = "confirm"
ATTR_CONFIRM_LIFE_SAFETY = "confirm_life_safety"
ATTR_ZONE_NUMBER = "zone_number"
ATTR_ZONE_TYPE = "zone_type"
ATTR_PARTITION = "partition"
ATTR_REPORT_ENABLED = "report_enabled"
ATTR_HARDWIRE_TYPE = "hardwire_type"
ATTR_RESPONSE_TIME = "response_time"
ATTR_FIELD = "field"
ATTR_VALUE = "value"
ATTR_KEY = "key"
ATTR_ACTION = "action"

PROGRAM_ZONE_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_ZONE_NUMBER): vol.All(vol.Coerce(int), vol.Range(min=1, max=64)),
        vol.Required(ATTR_ZONE_TYPE): vol.All(vol.Coerce(int), vol.In(ZONE_TYPES)),
        vol.Required(ATTR_PARTITION): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
        vol.Optional(ATTR_REPORT_ENABLED, default=True): cv.boolean,
        vol.Optional(ATTR_HARDWIRE_TYPE, default=HardwireType.END_OF_LINE.value): vol.In(
            [t.value for t in HardwireType]
        ),
        vol.Optional(ATTR_RESPONSE_TIME, default=ResponseTime.MS_350.value): vol.In(
            [t.value for t in ResponseTime]
        ),
        vol.Required(ATTR_CONFIRM): vol.All(cv.boolean, vol.Equal(True)),
        vol.Optional(ATTR_CONFIRM_LIFE_SAFETY, default=False): cv.boolean,
    }
)

SET_SYSTEM_TIMING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_FIELD): vol.In([f.value for f in SystemTimingField]),
        vol.Required(ATTR_VALUE): vol.Coerce(int),
        vol.Required(ATTR_CONFIRM): vol.All(cv.boolean, vol.Equal(True)),
    }
)

PROGRAM_FUNCTION_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_KEY): vol.In([k.value for k in FunctionKeyLetter]),
        vol.Required(ATTR_PARTITION): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
        vol.Required(ATTR_ACTION): vol.All(vol.Coerce(int), vol.In([a.value for a in FunctionKeyAction])),
        vol.Required(ATTR_CONFIRM): vol.All(cv.boolean, vol.Equal(True)),
    }
)


def _get_coordinator(hass: HomeAssistant, entry_id: str):
    domain_data = hass.data.get(DOMAIN, {})
    coordinator = domain_data.get(entry_id)
    if coordinator is None:
        raise HomeAssistantError(f"No Vista Console config entry with id {entry_id!r}")
    return coordinator


def _require_installer_code(coordinator) -> str:
    if not coordinator.installer_code:
        raise HomeAssistantError(
            "Field programming needs an installer code. Set one in this "
            "integration's options (Settings -> Devices & Services -> Vista "
            "Console -> Configure) first."
        )
    return coordinator.installer_code


async def _send_program_mode_sequence(
    coordinator, partition: int, action_keystrokes: str
) -> None:
    installer_code = _require_installer_code(coordinator)
    full_sequence = build_program_mode_wrapper(installer_code, action_keystrokes)
    # allow_installer_mode=True: every one of these services always opens
    # Program Mode by design, gated on the service's own required `confirm`
    # field instead of the generic send_keystrokes confirmation flag.
    validate_keystrokes(full_sequence, allow_installer_mode=True)
    await coordinator.client.send_keystrokes(partition, full_sequence)


def async_register_field_programming_services(hass: HomeAssistant) -> None:
    """Register the guided field-programming services, if not already done."""
    if hass.services.has_service(DOMAIN, SERVICE_PROGRAM_ZONE):
        return

    async def _handle_program_zone(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        zone_type = call.data[ATTR_ZONE_TYPE]
        if zone_type in LIFE_SAFETY_ZONE_TYPE_CODES and not call.data[ATTR_CONFIRM_LIFE_SAFETY]:
            raise KeystrokeGuardError(
                f"Zone type {zone_type} ({ZONE_TYPES[zone_type].label}) is a "
                "life-safety type (fire/CO). Pass confirm_life_safety: true to "
                "confirm you intend this. Also remember: this integration "
                "cannot read back what type this zone currently is before "
                "overwriting it -- double-check at the physical keypad "
                "(installer code + # + 56) if you're not certain."
            )
        program = ZoneProgram(
            zone_number=call.data[ATTR_ZONE_NUMBER],
            zone_type=zone_type,
            partition=call.data[ATTR_PARTITION],
            report_enabled=call.data[ATTR_REPORT_ENABLED],
            hardwire_type=HardwireType(call.data[ATTR_HARDWIRE_TYPE]),
            response_time=ResponseTime(call.data[ATTR_RESPONSE_TIME]),
        )
        keystrokes = build_zone_program_keystrokes(program)
        await _send_program_mode_sequence(coordinator, program.partition, keystrokes)

    async def _handle_set_system_timing(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        field = SystemTimingField(call.data[ATTR_FIELD])
        keystrokes = build_system_timing_keystrokes(field, call.data[ATTR_VALUE])
        # System data fields aren't partition-scoped the way *56 zone entry
        # is; partition 1 is used for the keystroke send itself (the field
        # covers both partitions internally where applicable).
        await _send_program_mode_sequence(coordinator, 1, keystrokes)

    async def _handle_program_function_key(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        partition = call.data[ATTR_PARTITION]
        keystrokes = build_function_key_keystrokes(
            FunctionKeyLetter(call.data[ATTR_KEY]),
            partition,
            FunctionKeyAction(call.data[ATTR_ACTION]),
        )
        await _send_program_mode_sequence(coordinator, partition, keystrokes)

    hass.services.async_register(
        DOMAIN, SERVICE_PROGRAM_ZONE, _handle_program_zone, schema=PROGRAM_ZONE_SCHEMA
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SYSTEM_TIMING,
        _handle_set_system_timing,
        schema=SET_SYSTEM_TIMING_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PROGRAM_FUNCTION_KEY,
        _handle_program_function_key,
        schema=PROGRAM_FUNCTION_KEY_SCHEMA,
    )
