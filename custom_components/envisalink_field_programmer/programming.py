"""Guardrails around sending raw keystrokes to the panel.

The Envisalink TPI command 071 ("Send Keystroke String") is the same
mechanism used for everything from an ordinary zone bypass to opening full
installer field programming. On a real Vista panel, Program Mode is opened
by typing the installer code followed by 800 (e.g. "4112800" with the
factory-default code) -- see the ADEMCO VISTA-21iP/VISTA-21iPSIA
Programming Guide (K14488PRV3), "PROGRAMMING MODE COMMANDS" table. Once in
Program Mode, essentially everything about the panel can be reconfigured,
including fire-zone and UL-listing-relevant settings, and if the panel ends
up somewhere unexpected there is no read-back channel over TPI to tell what
state it's actually in (the protocol reports keypad LED bits, not display
text).

An earlier version of this guard blocked any sequence containing "*8",
based on a generic "installers mode" warning in the EnvisaLink TPI spec that
turns out to describe DSC-style panels, not Vista -- there is no "*8" menu
on a Vista panel at all. This module blocks the actual Vista trigger
(``<installer code>800``) instead.

This module is the single choke point every keystroke-sending code path
goes through, so that safety logic lives in exactly one place:

  * Everyday, user-level sequences (e.g. quick zone bypass, "*1..#") are
    allowed by default -- they never open Program Mode.
  * Any sequence that would open Program Mode is refused unless the caller
    explicitly opts in via ``confirm_installer_risk`` -- there is
    deliberately no way to do this from the Lovelace card's normal UI
    without an explicit confirmation step.
"""
from __future__ import annotations

import logging
import re

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import EnvisalinkClient
from .const import DOMAIN, PROGRAM_MODE_SUFFIX

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_KEYSTROKES = "send_keystrokes"
SERVICE_TOGGLE_ZONE_BYPASS = "toggle_zone_bypass"

ATTR_ENTRY_ID = "entry_id"
ATTR_PARTITION = "partition"
ATTR_KEYS = "keys"
ATTR_ZONE = "zone"
ATTR_CONFIRM_INSTALLER_RISK = "confirm_installer_risk"

# Generic fallback for when the configured installer code isn't available to
# check against directly: any run of 4-6 digits immediately followed by the
# Program Mode suffix. This is what an installer-code entry actually looks
# like on the wire, regardless of which code is in use.
_GENERIC_PROGRAM_MODE_PATTERN = re.compile(r"\d{4,6}" + re.escape(PROGRAM_MODE_SUFFIX))

# Only digits, *, and # are valid ECP keystrokes per the TPI spec.
_VALID_KEYSTROKE_CHARS = set("0123456789*#")

SEND_KEYSTROKES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_PARTITION): vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
        vol.Required(ATTR_KEYS): cv.string,
        vol.Optional(ATTR_CONFIRM_INSTALLER_RISK, default=False): cv.boolean,
    }
)

TOGGLE_ZONE_BYPASS_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_ENTRY_ID): cv.string,
        vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=1, max=64)),
    }
)


class KeystrokeGuardError(HomeAssistantError):
    """Raised when a keystroke sequence is refused by the safety guard."""


def _contains_program_mode_entry(keys: str, installer_code: str | None) -> bool:
    if installer_code and f"{installer_code}{PROGRAM_MODE_SUFFIX}" in keys:
        return True
    return bool(_GENERIC_PROGRAM_MODE_PATTERN.search(keys))


def validate_keystrokes(
    keys: str,
    *,
    allow_installer_mode: bool = False,
    installer_code: str | None = None,
) -> None:
    """Raise KeystrokeGuardError if ``keys`` is unsafe to send unattended."""
    if not keys:
        raise KeystrokeGuardError("Keystroke string must not be empty")

    invalid_chars = set(keys) - _VALID_KEYSTROKE_CHARS
    if invalid_chars:
        raise KeystrokeGuardError(
            f"Invalid keystroke characters {sorted(invalid_chars)!r}; "
            "only digits, '*', and '#' are valid on a Vista keypad"
        )

    if not allow_installer_mode and _contains_program_mode_entry(keys, installer_code):
        raise KeystrokeGuardError(
            f"Refusing to send {keys!r}: this looks like it opens Program Mode "
            "(installer code followed by 800). Program Mode gives access to "
            "every data field on the panel, including fire-zone and "
            "UL-listing-relevant settings, and the TPI protocol has no way to "
            "read back what's actually on the keypad display while there. "
            "Pass confirm_installer_risk: true if you deliberately intend this "
            "and understand the risk."
        )


async def async_send_guarded_keystrokes(
    client: EnvisalinkClient,
    partition: int,
    keys: str,
    *,
    allow_installer_mode: bool = False,
    installer_code: str | None = None,
) -> None:
    """Validate ``keys`` against the safety guard, then send them."""
    validate_keystrokes(
        keys, allow_installer_mode=allow_installer_mode, installer_code=installer_code
    )
    await client.send_keystrokes(partition, keys)


def _get_coordinator(hass: HomeAssistant, entry_id: str):
    domain_data = hass.data.get(DOMAIN, {})
    coordinator = domain_data.get(entry_id)
    if coordinator is None:
        raise HomeAssistantError(f"No Envisalink Field Programmer config entry with id {entry_id!r}")
    return coordinator


def async_register_services(hass: HomeAssistant) -> None:
    """Register the envisalink_field_programmer.* services, if not already registered."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_KEYSTROKES):
        return

    async def _handle_send_keystrokes(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        await async_send_guarded_keystrokes(
            coordinator.client,
            call.data[ATTR_PARTITION],
            call.data[ATTR_KEYS],
            allow_installer_mode=call.data[ATTR_CONFIRM_INSTALLER_RISK],
            installer_code=coordinator.installer_code,
        )

    async def _handle_toggle_zone_bypass(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        zone_number = call.data[ATTR_ZONE]
        zone = coordinator.data.zone(zone_number)
        keys = f"*1{zone_number:02d}#"
        await async_send_guarded_keystrokes(coordinator.client, zone.partition, keys)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_KEYSTROKES,
        _handle_send_keystrokes,
        schema=SEND_KEYSTROKES_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TOGGLE_ZONE_BYPASS,
        _handle_toggle_zone_bypass,
        schema=TOGGLE_ZONE_BYPASS_SCHEMA,
    )
