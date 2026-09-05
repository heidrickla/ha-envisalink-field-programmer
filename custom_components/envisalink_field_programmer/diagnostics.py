"""Diagnostics support.

Also doubles as the closest thing to a "backup" this integration can offer:
downloading diagnostics captures a timestamped snapshot of every
partition/zone/system flag known to Home Assistant at that moment (armed
state, open/bypassed zones, trouble flags, last user, etc.) as plain JSON,
which is worth keeping around before you experiment with anything in
programming.py.

Important limitation: this is NOT a backup of the panel's installer field
programming (zone types, entry/exit delays, alpha descriptors, output
assignments, etc.). The EnvisaLink TPI protocol has no command that reads
those values back -- section 3 of the TPI doc only exposes live status
events and keypad-LED state, never the underlying *56/*58/*79/*80/*82-style
configuration data. The only ways to capture that are the installer
programming menu itself (walk each field at the keypad and record it) or a
Honeywell-side tool (Compass Downloader / Total Connect installer access),
neither of which this integration can reach.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_INSTALLER_CODE, CONF_PASSWORD, CONF_USER_CODE
from .coordinator import VistaConsoleConfigEntry

TO_REDACT = {CONF_PASSWORD, CONF_USER_CODE, CONF_INSTALLER_CODE}


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
            "flags as last reported by the panel over Envisalink). It is NOT "
            "a backup of installer field programming -- the TPI protocol "
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
