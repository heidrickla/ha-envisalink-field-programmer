"""The guided field-programming operations, and the actions that expose them.

Every operation here always opens Program Mode (installer code + 800), so
unlike the general-purpose ``send_keystrokes`` action, there is no "safe by
default" path -- a confirmation is required for every write. Setting a zone to
(or off of) a fire/CO zone type additionally requires a life-safety
confirmation, since the TPI protocol cannot read back a zone's *current* type
before overwriting it (see field_programming.py).

The three ``async_program_*`` coroutines below are the operations themselves,
and the only place the guards live. The actions in this module and the buttons
on the panel device (button.py) are two front ends onto the same three
coroutines: an automation calls the action with its values in the call, and a
person on the device page sets the config entities and presses the button. A
guard added here therefore applies to both, which is why the buttons build no
keystrokes of their own.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    DOMAIN,
    SERVICE_PROGRAM_FUNCTION_KEY,
    SERVICE_PROGRAM_ZONE,
    SERVICE_SET_SYSTEM_TIMING,
)
from .coordinator import VistaConsoleCoordinator
from .field_programming import (
    LIFE_SAFETY_ZONE_TYPE_CODES,
    ZONE_TYPES,
    FunctionKeyAction,
    FunctionKeyLetter,
    HardwireType,
    ResponseTime,
    ZoneProgram,
    build_function_key_keystrokes,
    build_zone_program_keystrokes,
)
from .panels import GuidedOp, Verification
from .programming import (
    KeystrokeGuardError,
    async_send_guarded_keystrokes,
    get_loaded_coordinator,
)

_LOGGER = logging.getLogger(__name__)

ATTR_ENTRY_ID = "entry_id"
ATTR_CONFIRM = "confirm"
ATTR_CONFIRM_LIFE_SAFETY = "confirm_life_safety"
ATTR_CONFIRM_UNVERIFIED_MODEL = "confirm_unverified_model"
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
        vol.Optional(ATTR_CONFIRM_UNVERIFIED_MODEL, default=False): cv.boolean,
    }
)

# The valid timing field ids and value ranges differ by dialect (residential
# *34/*35/*36/*84 vs. commercial *09-*12), so ``field`` is a plain string here
# and is validated at runtime against the selected model's dialect. ``partition``
# matters only for dialects with partition-specific timing (commercial).
SET_SYSTEM_TIMING_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_FIELD): cv.string,
        vol.Required(ATTR_VALUE): vol.Coerce(int),
        vol.Optional(ATTR_PARTITION, default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
        vol.Required(ATTR_CONFIRM): vol.All(cv.boolean, vol.Equal(True)),
        vol.Optional(ATTR_CONFIRM_UNVERIFIED_MODEL, default=False): cv.boolean,
    }
)

PROGRAM_FUNCTION_KEY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_KEY): vol.In([k.value for k in FunctionKeyLetter]),
        vol.Required(ATTR_PARTITION): vol.All(vol.Coerce(int), vol.Range(min=1, max=3)),
        vol.Required(ATTR_ACTION): vol.All(
            vol.Coerce(int), vol.In([a.value for a in FunctionKeyAction])
        ),
        vol.Required(ATTR_CONFIRM): vol.All(cv.boolean, vol.Equal(True)),
        vol.Optional(ATTR_CONFIRM_UNVERIFIED_MODEL, default=False): cv.boolean,
    }
)


def _require_installer_code(coordinator: VistaConsoleCoordinator) -> str:
    if not coordinator.installer_code:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_installer_code",
        )
    return coordinator.installer_code


def _require_guided_support(coordinator: VistaConsoleCoordinator, op: GuidedOp) -> None:
    """Refuse a guided operation the selected model's dialect doesn't drive.

    Each dialect declares which of ZONE / TIMING / FUNCTION_KEY it supports.
    E.g. commercial VISTA supports TIMING only (its #93 zone menu is not driven
    blind), and DSC supports none (positional whole-section programming +
    Honeywell-only transport). Refuse loudly rather than build meaningless (and
    potentially destructive) keystrokes.
    """
    if op not in coordinator.dialect.supported_guided_ops:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="guided_op_unsupported",
            translation_placeholders={
                "operation": op.value,
                "model": coordinator.panel_model.label,
                "note": coordinator.dialect.guided_field_programming_note,
            },
        )


def _require_verified_or_ack(
    coordinator: VistaConsoleCoordinator, confirm_unverified: bool
) -> None:
    """Gate non-VERIFIED models behind an explicit acknowledgment.

    Only the VISTA-21iP is built from its own programming guide. Every other
    model's field data is inherited or provisional (see panels/), so field
    programming against it must be explicitly acknowledged -- keystrokes that
    are wrong for the actual panel can disable a fire zone or lock up the
    panel, and there's no read-back over TPI to catch it.
    """
    model = coordinator.panel_model
    if model.verification == Verification.VERIFIED:
        return
    if not confirm_unverified:
        raise KeystrokeGuardError(
            translation_domain=DOMAIN,
            translation_key="unverified_model",
            translation_placeholders={
                "model": model.label,
                "verification": model.verification.value,
                "notes": model.notes,
            },
        )


async def _send_program_mode_sequence(
    coordinator: VistaConsoleCoordinator,
    partition: int,
    action_keystrokes: str,
    *,
    op: GuidedOp,
    confirm_unverified: bool,
) -> None:
    _require_guided_support(coordinator, op)
    _require_verified_or_ack(coordinator, confirm_unverified)
    installer_code = _require_installer_code(coordinator)
    full_sequence = coordinator.dialect.program_mode_wrapper(installer_code, action_keystrokes)
    # allow_installer_mode=True: every one of these operations always opens
    # Program Mode by design, gated on the caller's own confirmation instead of
    # the generic send_keystrokes confirmation flag. The coordinator's dialect
    # selects the correct family guard, and the guarded sender turns a refused
    # or unacknowledged command into HomeAssistantError.
    await async_send_guarded_keystrokes(
        coordinator.client,
        partition,
        full_sequence,
        allow_installer_mode=True,
        dialect=coordinator.dialect,
    )


async def async_program_zone(
    coordinator: VistaConsoleCoordinator,
    *,
    zone_number: int,
    zone_type: int,
    partition: int,
    report_enabled: bool = True,
    hardwire_type: HardwireType = HardwireType.END_OF_LINE,
    response_time: ResponseTime = ResponseTime.MS_350,
    confirm_life_safety: bool = False,
    confirm_unverified_model: bool = False,
) -> None:
    """Program one zone's *56 settings, guards and all."""
    if zone_type in LIFE_SAFETY_ZONE_TYPE_CODES and not confirm_life_safety:
        raise KeystrokeGuardError(
            translation_domain=DOMAIN,
            translation_key="life_safety_zone_type",
            translation_placeholders={
                "zone_type": str(zone_type),
                "label": ZONE_TYPES[zone_type].label,
            },
        )
    program = ZoneProgram(
        zone_number=zone_number,
        zone_type=zone_type,
        partition=partition,
        report_enabled=report_enabled,
        hardwire_type=hardwire_type,
        response_time=response_time,
    )
    await _send_program_mode_sequence(
        coordinator,
        program.partition,
        build_zone_program_keystrokes(program),
        op=GuidedOp.ZONE,
        confirm_unverified=confirm_unverified_model,
    )


async def async_set_system_timing(
    coordinator: VistaConsoleCoordinator,
    *,
    field: str,
    value: int,
    partition: int = 1,
    confirm_unverified_model: bool = False,
) -> None:
    """Edit one system-timing data field, guards and all."""
    # Guard the operation early so the error is "not available for <model>"
    # rather than an unknown-field ValueError from an empty timing table.
    _require_guided_support(coordinator, GuidedOp.TIMING)
    valid = coordinator.dialect.timing_fields()
    if field not in valid:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_timing_field",
            translation_placeholders={
                "field": field,
                "model": coordinator.panel_model.label,
                "valid": ", ".join(sorted(valid)),
            },
        )
    # The value range depends on the field and the dialect, so the schema
    # cannot check it; the builder's ValueError is the user's mistake.
    try:
        keystrokes = coordinator.dialect.build_timing_keystrokes(field, value, partition)
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_timing_value",
            translation_placeholders={"error": str(err)},
        ) from err
    await _send_program_mode_sequence(
        coordinator,
        partition,
        keystrokes,
        op=GuidedOp.TIMING,
        confirm_unverified=confirm_unverified_model,
    )


async def async_program_function_key(
    coordinator: VistaConsoleCoordinator,
    *,
    key: FunctionKeyLetter,
    partition: int,
    action: FunctionKeyAction,
    confirm_unverified_model: bool = False,
) -> None:
    """Assign one A/B/C/D function key, guards and all."""
    keystrokes = build_function_key_keystrokes(key, partition, action)
    await _send_program_mode_sequence(
        coordinator,
        partition,
        keystrokes,
        op=GuidedOp.FUNCTION_KEY,
        confirm_unverified=confirm_unverified_model,
    )


@callback
def async_register_field_programming_services(hass: HomeAssistant) -> None:
    """Register the guided field-programming services, once, from async_setup."""

    async def _handle_program_zone(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        await async_program_zone(
            coordinator,
            zone_number=call.data[ATTR_ZONE_NUMBER],
            zone_type=call.data[ATTR_ZONE_TYPE],
            partition=call.data[ATTR_PARTITION],
            report_enabled=call.data[ATTR_REPORT_ENABLED],
            hardwire_type=HardwireType(call.data[ATTR_HARDWIRE_TYPE]),
            response_time=ResponseTime(call.data[ATTR_RESPONSE_TIME]),
            confirm_life_safety=call.data[ATTR_CONFIRM_LIFE_SAFETY],
            confirm_unverified_model=call.data[ATTR_CONFIRM_UNVERIFIED_MODEL],
        )

    async def _handle_set_system_timing(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        await async_set_system_timing(
            coordinator,
            field=call.data[ATTR_FIELD],
            value=call.data[ATTR_VALUE],
            partition=call.data[ATTR_PARTITION],
            confirm_unverified_model=call.data[ATTR_CONFIRM_UNVERIFIED_MODEL],
        )

    async def _handle_program_function_key(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        await async_program_function_key(
            coordinator,
            key=FunctionKeyLetter(call.data[ATTR_KEY]),
            partition=call.data[ATTR_PARTITION],
            action=FunctionKeyAction(call.data[ATTR_ACTION]),
            confirm_unverified_model=call.data[ATTR_CONFIRM_UNVERIFIED_MODEL],
        )

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
