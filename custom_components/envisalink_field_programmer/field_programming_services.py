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
            "Field programming needs an installer code. Set one in this "
            "integration's options (Settings -> Devices & Services -> "
            "Envisalink Field Programmer -> Configure) first."
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
            f"Guided {op.value} programming is not available for "
            f"{coordinator.panel_model.label}. " + coordinator.dialect.guided_field_programming_note
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
            f"{model.label} is not verified against its own programming guide "
            f"({model.verification.value}): {model.notes} Field numbers/zone-type "
            "codes may be wrong for this exact panel, and this integration "
            "cannot read back the panel to catch a mistake. Pass "
            "confirm_unverified_model: true to proceed anyway, and verify the "
            "result at the physical keypad."
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
    # allow_installer_mode=True: every one of these services always opens
    # Program Mode by design, gated on the service's own required `confirm`
    # field instead of the generic send_keystrokes confirmation flag. The
    # coordinator's dialect selects the correct family guard, and the guarded
    # sender turns a refused or unacknowledged command into HomeAssistantError.
    await async_send_guarded_keystrokes(
        coordinator.client,
        partition,
        full_sequence,
        allow_installer_mode=True,
        dialect=coordinator.dialect,
    )


@callback
def async_register_field_programming_services(hass: HomeAssistant) -> None:
    """Register the guided field-programming services, once, from async_setup."""

    async def _handle_program_zone(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
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
        await _send_program_mode_sequence(
            coordinator,
            program.partition,
            keystrokes,
            op=GuidedOp.ZONE,
            confirm_unverified=call.data[ATTR_CONFIRM_UNVERIFIED_MODEL],
        )

    async def _handle_set_system_timing(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        # Guard the operation early so the error is "not available for <model>"
        # rather than an unknown-field ValueError from an empty timing table.
        _require_guided_support(coordinator, GuidedOp.TIMING)
        field = call.data[ATTR_FIELD]
        valid = coordinator.dialect.timing_fields()
        if field not in valid:
            raise ServiceValidationError(
                f"Timing field {field!r} is not valid for "
                f"{coordinator.panel_model.label}. Valid fields: "
                f"{', '.join(sorted(valid))}."
            )
        partition = call.data[ATTR_PARTITION]
        # The value range depends on the field and the dialect, so the schema
        # cannot check it; the builder's ValueError is the user's mistake.
        try:
            keystrokes = coordinator.dialect.build_timing_keystrokes(
                field, call.data[ATTR_VALUE], partition
            )
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await _send_program_mode_sequence(
            coordinator,
            partition,
            keystrokes,
            op=GuidedOp.TIMING,
            confirm_unverified=call.data[ATTR_CONFIRM_UNVERIFIED_MODEL],
        )

    async def _handle_program_function_key(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        partition = call.data[ATTR_PARTITION]
        keystrokes = build_function_key_keystrokes(
            FunctionKeyLetter(call.data[ATTR_KEY]),
            partition,
            FunctionKeyAction(call.data[ATTR_ACTION]),
        )
        await _send_program_mode_sequence(
            coordinator,
            partition,
            keystrokes,
            op=GuidedOp.FUNCTION_KEY,
            confirm_unverified=call.data[ATTR_CONFIRM_UNVERIFIED_MODEL],
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
