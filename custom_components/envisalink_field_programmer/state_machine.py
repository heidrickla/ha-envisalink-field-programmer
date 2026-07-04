"""Pure logic that folds a stream of TPIEvents into a VistaState.

Kept separate from the coordinator so the event -> state transitions can be
unit tested with plain TPIEvent objects, no asyncio or Home Assistant
required.
"""
from __future__ import annotations

import logging

from .client import TPIEvent
from .const import INSTALLERS_MODE_EVENT_CODES
from .models import ARM_MODE_TO_STATE, VistaState

_LOGGER = logging.getLogger(__name__)

# Any of these events being observed is proof the affected partition is back
# under normal keybus supervision -- used to clear the "installers mode"
# safety flag, since the TPI protocol has no explicit "left installers mode"
# event of its own (see TPI doc section 3.6).
_NORMAL_OPERATION_EVENT_CODES = {"650", "651", "652", "655"}


def _parse_bypass_bitfield(hex_string: str, num_zones: int) -> dict[int, bool]:
    """Decode the 616 bypassed-zones bitfield (8 bytes, lower zones first)."""
    result: dict[int, bool] = {}
    try:
        raw = bytes.fromhex(hex_string)
    except ValueError:
        _LOGGER.warning("Malformed bypass bitfield: %r", hex_string)
        return result
    for zone in range(1, num_zones + 1):
        byte_index, bit_index = divmod(zone - 1, 8)
        if byte_index >= len(raw):
            break
        result[zone] = bool(raw[byte_index] & (1 << bit_index))
    return result


def apply_event(state: VistaState, event: TPIEvent) -> None:
    """Mutate ``state`` in place to reflect ``event``. Unknown codes are ignored."""
    code = event.code

    if code in INSTALLERS_MODE_EVENT_CODES:
        state.system.installers_mode = True
        return
    if code in _NORMAL_OPERATION_EVENT_CODES:
        state.system.installers_mode = False

    if code in ("601", "602", "603", "604"):
        zone = state.zone(event.zone)
        if event.partition:
            zone.partition = event.partition
        if code == "601":
            zone.alarm = True
        elif code == "602":
            zone.alarm = False
        elif code == "603":
            zone.tamper = True
        elif code == "604":
            zone.tamper = False
        return

    if code in ("605", "606", "609", "610"):
        zone = state.zone(event.zone)
        if code == "605":
            zone.fault = True
        elif code == "606":
            zone.fault = False
        elif code == "609":
            zone.open = True
        elif code == "610":
            zone.open = False
        return

    if code == "616":
        bypass_map = _parse_bypass_bitfield(event.fields["bypass_bitfield"], len(state.zones) or 64)
        for zone_number, bypassed in bypass_map.items():
            state.zone(zone_number).bypassed = bypassed
        return

    if code == "650":
        partition = state.partition(event.partition)
        partition.ready = True
        partition.busy = False
        partition.force_arm_enabled = False
        return
    if code == "651":
        state.partition(event.partition).ready = False
        return
    if code == "652":
        partition = state.partition(event.partition)
        partition.armed = True
        partition.arm_state = ARM_MODE_TO_STATE.get(event.fields.get("mode", ""), "armed_away")
        partition.exit_delay = False
        partition.failed_to_arm = False
        return
    if code == "653":
        partition = state.partition(event.partition)
        partition.ready = True
        partition.force_arm_enabled = True
        return
    if code == "654":
        state.partition(event.partition).alarm = True
        return
    if code == "655":
        partition = state.partition(event.partition)
        partition.armed = False
        partition.arm_state = "disarmed"
        partition.alarm = False
        partition.exit_delay = False
        partition.entry_delay = False
        return
    if code == "656":
        state.partition(event.partition).exit_delay = True
        return
    if code == "657":
        state.partition(event.partition).entry_delay = True
        return
    if code == "658":
        state.partition(event.partition).keypad_lockout = True
        return
    if code == "659":
        partition = state.partition(event.partition)
        partition.failed_to_arm = True
        partition.armed = False
        return
    if code == "663":
        state.partition(event.partition).chime_enabled = True
        return
    if code == "664":
        state.partition(event.partition).chime_enabled = False
        return
    if code == "673":
        state.partition(event.partition).busy = True
        return
    if code == "674":
        state.partition(event.partition).exit_delay = True
        return
    if code in ("700", "750"):
        state.partition(event.partition).last_user = event.fields.get("user")
        return

    if code == "800":
        state.system.battery_trouble = True
        return
    if code == "801":
        state.system.battery_trouble = False
        return
    if code == "802":
        state.system.ac_trouble = True
        return
    if code == "803":
        state.system.ac_trouble = False
        return
    if code == "806":
        state.system.bell_trouble = True
        return
    if code == "807":
        state.system.bell_trouble = False
        return
    if code == "814":
        state.system.ftc_trouble = True
        return
    if code == "815":
        state.system.ftc_trouble = False
        return
    if code == "829":
        state.system.general_tamper = True
        return
    if code == "830":
        state.system.general_tamper = False
        return
    if code == "840":
        state.partition(event.partition).trouble = True
        return
    if code == "841":
        state.partition(event.partition).trouble = False
        return
    if code == "842":
        state.system.fire_trouble = True
        return
    if code == "843":
        state.system.fire_trouble = False
        return

    # 500/501/502/505/510/511/550/560-562/615/9xx and any unrecognized code:
    # no state effect here; the coordinator may still log/surface these for
    # diagnostics.
