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
from typing import TYPE_CHECKING

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .client import EnvisalinkClient, TPIError
from .const import DOMAIN, SERVICE_SEND_KEYSTROKES, SERVICE_TOGGLE_ZONE_BYPASS
from .panels import PanelDialect, get_dialect

if TYPE_CHECKING:
    from .coordinator import VistaConsoleCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_ENTRY_ID = "entry_id"
ATTR_PARTITION = "partition"
ATTR_KEYS = "keys"
ATTR_ZONE = "zone"
ATTR_CONFIRM_INSTALLER_RISK = "confirm_installer_risk"

# Only digits, *, and # are valid ECP keystrokes per the TPI spec (true for
# both the Honeywell and DSC keypad character sets).
_VALID_KEYSTROKE_CHARS = set("0123456789*#")

# A keystroke string can embed a secret: the installer code (4-6 digits) or a
# user/arm-disarm code. Any run of 4+ consecutive digits is a code; mask it
# before the string reaches a log, service error, or the Lovelace card, which
# surfaces guard errors verbatim. The `*`/`#`/`800`/`*56` operators (<4 digits)
# are kept so the message still explains *why* a sequence was refused.
_CODE_RUN = re.compile(r"\d{4,}")


def _redact_codes(keys: str) -> str:
    """Mask runs of 4+ digits (installer/user codes) for safe display."""
    return _CODE_RUN.sub("[code]", keys)


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


class KeystrokeGuardError(ServiceValidationError):
    """Raised when a keystroke sequence is refused by the safety guard.

    A refusal is a verdict on the caller's input, not a device failure, so it
    is a validation error: Home Assistant shows it without a traceback.
    """


def validate_keystrokes(
    keys: str,
    *,
    allow_installer_mode: bool = False,
    installer_code: str | None = None,
    dialect: PanelDialect | None = None,
) -> None:
    """Raise KeystrokeGuardError if ``keys`` is unsafe to send unattended.

    ``dialect`` selects the panel family whose Program-Mode trigger to guard
    against (VISTA's ``<code>800`` vs. DSC's ``*8<code>``). It defaults to the
    VISTA dialect, preserving the original single-panel behaviour for callers
    that don't pass one.
    """
    if not keys:
        raise KeystrokeGuardError(
            translation_domain=DOMAIN,
            translation_key="empty_keystrokes",
        )

    invalid_chars = set(keys) - _VALID_KEYSTROKE_CHARS
    if invalid_chars:
        raise KeystrokeGuardError(
            translation_domain=DOMAIN,
            translation_key="invalid_keystroke_characters",
            translation_placeholders={"characters": " ".join(sorted(invalid_chars))},
        )

    if dialect is None:
        dialect = get_dialect(None)  # VISTA-21iP default

    if not allow_installer_mode and dialect.opens_program_mode(keys, installer_code):
        raise KeystrokeGuardError(
            translation_domain=DOMAIN,
            translation_key="opens_program_mode",
            translation_placeholders={"keys": _redact_codes(keys)},
        )


async def async_send_guarded_keystrokes(
    client: EnvisalinkClient,
    partition: int,
    keys: str,
    *,
    allow_installer_mode: bool = False,
    installer_code: str | None = None,
    dialect: PanelDialect | None = None,
) -> None:
    """Validate ``keys`` against the safety guard, then send them."""
    validate_keystrokes(
        keys,
        allow_installer_mode=allow_installer_mode,
        installer_code=installer_code,
        dialect=dialect,
    )
    try:
        await client.send_keystrokes(partition, keys)
    except TPIError as err:
        # Surface transport/ack failures as a HomeAssistantError so service
        # calls (and the Lovelace card) show the real reason instead of a
        # generic "Unknown error" + log traceback.
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="keystrokes_not_accepted",
            translation_placeholders={"error": str(err)},
        ) from err


def get_loaded_coordinator(hass: HomeAssistant, entry_id: str) -> VistaConsoleCoordinator:
    """The loaded coordinator an action call names, or a translated refusal."""
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="not_loaded",
            translation_placeholders={"name": entry.title},
        )
    coordinator: VistaConsoleCoordinator = entry.runtime_data
    return coordinator


@callback
def async_register_services(hass: HomeAssistant) -> None:
    """Register send_keystrokes and toggle_zone_bypass, once, from async_setup."""

    async def _handle_send_keystrokes(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        await async_send_guarded_keystrokes(
            coordinator.client,
            call.data[ATTR_PARTITION],
            call.data[ATTR_KEYS],
            allow_installer_mode=call.data[ATTR_CONFIRM_INSTALLER_RISK],
            installer_code=coordinator.installer_code,
            # Use the entry's actual dialect so the guard checks *this* panel's
            # installer-mode trigger (DSC ``*8<code>`` vs. VISTA ``<code>800``).
            # Without this the guard would default to VISTA and let a DSC
            # installer-mode sequence through unconfirmed.
            dialect=coordinator.dialect,
        )

    async def _handle_toggle_zone_bypass(call: ServiceCall) -> None:
        coordinator = get_loaded_coordinator(hass, call.data[ATTR_ENTRY_ID])
        zone_number = call.data[ATTR_ZONE]
        zone = coordinator.data.zone(zone_number)
        keys = f"*1{zone_number:02d}#"
        await async_send_guarded_keystrokes(
            coordinator.client, zone.partition, keys, dialect=coordinator.dialect
        )

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
