"""Diagnostics support.

A download is a timestamped JSON snapshot of every partition, zone and system
flag Home Assistant holds at that moment: armed state, open and bypassed
zones, trouble flags, last user. That is the closest thing to a backup this
integration can offer, and it is worth taking one before using programming.py.

It is not a backup of the panel's installer field programming: zone types,
entry and exit delays, alpha descriptors, output assignments. TPI section 3
exposes live status events and keypad-LED state only, never the underlying
*56/*58/*79/*80/*82 configuration data, so no command reads those values back.
They can be captured by walking each field at the keypad, or with a
Honeywell-side tool such as Compass Downloader or Total Connect installer
access. This integration reaches neither.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_MAC,
    CONF_PASSWORD,
    CONF_USER_CODE,
    CONF_ZONE_NAMES,
)
from .coordinator import VistaConsoleConfigEntry

# A diagnostics file is downloaded to be pasted into a public issue. Besides
# the three secrets, the config entry holds the panel's address on the user's
# LAN, the module's MAC, and whatever text the user typed as zone names, which
# names rooms and people. None of them is needed to read a report.
TO_REDACT = {
    CONF_PASSWORD,
    CONF_USER_CODE,
    CONF_INSTALLER_CODE,
    CONF_HOST,
    CONF_MAC,
    CONF_ZONE_NAMES,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: VistaConsoleConfigEntry
) -> dict[str, Any]:
    """Return a redacted config plus a live state snapshot."""
    coordinator = entry.runtime_data
    state = coordinator.data

    return {
        "captured_at": datetime.now(UTC).isoformat(),
        "note": (
            "This is a live-state snapshot only (armed/open/bypass/trouble "
            "flags as last reported by the panel over Envisalink). It is not "
            "a backup of installer field programming: the TPI protocol "
            "cannot read that back. See diagnostics.py docstring."
        ),
        "config_entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "system": dataclasses.asdict(state.system),
        "partitions": {
            str(number): dataclasses.asdict(partition)
            for number, partition in sorted(state.partitions.items())
        },
        "zones": {
            str(number): dataclasses.asdict(zone) for number, zone in sorted(state.zones.items())
        },
        "last_event": (
            {
                "code": coordinator.last_event.code,
                "name": coordinator.last_event.name,
                "fields": coordinator.last_event.fields,
            }
            if coordinator.last_event is not None
            else None
        ),
        # What the device page's programming form holds and what became of the
        # last button press. Neither is panel state; both are what a report of
        # "I programmed a zone and nothing happened" needs. No code is in
        # either: the form holds field values, and a refusal that quotes a
        # keystroke sequence has already had every run of four or more digits
        # masked (see programming.py).
        "field_programming": {
            "supported_operations": sorted(
                op.value for op in coordinator.dialect.supported_guided_ops
            ),
            "installer_code_set": bool(coordinator.installer_code),
            "form": dataclasses.asdict(coordinator.programming),
            "last_result": (
                dataclasses.asdict(coordinator.last_programming_result)
                if coordinator.last_programming_result is not None
                else None
            ),
        },
    }
