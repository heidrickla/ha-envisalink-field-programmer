"""Guardrails around sending raw keystrokes to the panel.

The Envisalink TPI command 071 ("Send Keystroke String") is the same
mechanism used for everything from an ordinary zone bypass to entering full
installer field programming (*8 on the keypad). The EnvisaLink TPI
Programmer's Document itself calls this out (section 3.6, "Installers Mode
- Warning"): sending the wrong keystrokes can put the panel into installers
mode, where most functions -- including disarm -- are locked out until
someone physically power-cycles the panel. Installer mode is also where
fire-zone and UL-listing-relevant settings live, so an accidental or
scripted keystroke sequence here is not a "just retry" failure mode.

This module is the single choke point every keystroke-sending code path
goes through, so that safety logic lives in exactly one place:

  * Everyday, user-level sequences (e.g. quick zone bypass, "*1..#") are
    allowed by default.
  * Any sequence that would enter installers mode ("*8") is refused unless
    the caller explicitly opts in *and* the config entry allows it -- there
    is deliberately no way to do this from the Lovelace card without going
    through the raw service call and its confirmation field.
"""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .client import EnvisalinkClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_KEYSTROKES = "send_keystrokes"
SERVICE_TOGGLE_ZONE_BYPASS = "toggle_zone_bypass"

ATTR_ENTRY_ID = "entry_id"
ATTR_PARTITION = "partition"
ATTR_KEYS = "keys"
ATTR_ZONE = "zone"
ATTR_CONFIRM_INSTALLER_RISK = "confirm_installer_risk"

# Sequences that enter, or could plausibly enter, installer-level
# programming on a Vista panel. Blocked unless explicitly confirmed.
_INSTALLER_MODE_TRIGGERS = ("*8",)

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


def validate_keystrokes(keys: str, *, allow_installer_mode: bool = False) -> None:
    """Raise KeystrokeGuardError if ``keys`` is unsafe to send unattended."""
    if not keys:
        raise KeystrokeGuardError("Keystroke string must not be empty")

    invalid_chars = set(keys) - _VALID_KEYSTROKE_CHARS
    if invalid_chars:
        raise KeystrokeGuardError(
            f"Invalid keystroke characters {sorted(invalid_chars)!r}; "
            "only digits, '*', and '#' are valid on a Vista keypad"
        )

    if not allow_installer_mode:
        for trigger in _INSTALLER_MODE_TRIGGERS:
            if trigger in keys:
                raise KeystrokeGuardError(
                    f"Refusing to send {keys!r}: contains {trigger!r}, which enters "
                    "installer programming mode. Vista panels can dead-lock in "
                    "installer mode (see EnvisaLink TPI doc section 3.6) until the "
                    "panel is power-cycled, and installer mode governs fire-zone and "
                    "UL-listing-relevant settings. Pass confirm_installer_risk: true "
                    "to the send_keystrokes service if you deliberately intend to "
                    "enter installer programming and understand the risk."
                )


async def async_send_guarded_keystrokes(
    client: EnvisalinkClient,
    partition: int,
    keys: str,
    *,
    allow_installer_mode: bool = False,
) -> None:
    """Validate ``keys`` against the safety guard, then send them."""
    validate_keystrokes(keys, allow_installer_mode=allow_installer_mode)
    await client.send_keystrokes(partition, keys)


def _get_coordinator(hass: HomeAssistant, entry_id: str):
    domain_data = hass.data.get(DOMAIN, {})
    coordinator = domain_data.get(entry_id)
    if coordinator is None:
        raise HomeAssistantError(f"No Vista Console config entry with id {entry_id!r}")
    return coordinator


def async_register_services(hass: HomeAssistant) -> None:
    """Register the vista_console.* services, if not already registered."""
    if hass.services.has_service(DOMAIN, SERVICE_SEND_KEYSTROKES):
        return

    async def _handle_send_keystrokes(call: ServiceCall) -> None:
        coordinator = _get_coordinator(hass, call.data[ATTR_ENTRY_ID])
        await async_send_guarded_keystrokes(
            coordinator.client,
            call.data[ATTR_PARTITION],
            call.data[ATTR_KEYS],
            allow_installer_mode=call.data[ATTR_CONFIRM_INSTALLER_RISK],
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
