"""Pure logic that folds a stream of TPIEvents into a VistaState.

Kept separate from the coordinator so the event -> state transitions can be
unit tested with plain TPIEvent objects, no asyncio or Home Assistant
required.

Two events carry everything folded here. See client.py's module docstring for
the wire format.

  * ``%00`` (keypad update): a 16-bit icon-LED bitfield per partition, the
    only source of partition status over this protocol for a Honeywell
    panel: ready, armed, alarm, trouble.
  * ``%FF`` (zone timer dump): the authoritative source of zone open/closed
    state, requested periodically by the coordinator via
    ``EnvisalinkClient.dump_zone_timers()``.

``%01`` and ``%02`` (zone and partition state change) are ignored. The
`pyenvisalink` reference implementation documents them as no-ops for
Honeywell panels, which report state through keypad updates and CID events
only.
"""

from __future__ import annotations

import logging
import re
from enum import Enum

from .client import TPIEvent
from .const import (
    ARM_DISARM_CID_EVENTS,
    CID_QUALIFIER_CLOSING,
    CID_QUALIFIER_OPENING,
    EVT_KEYPAD_UPDATE,
    EVT_REALTIME_CID_EVENT,
    EVT_ZONE_TIMER_DUMP,
    ICON_LED_BITS,
    INSTALLERS_MODE_CID_EVENT,
    INSTALLERS_MODE_EXIT_CID_EVENT,
)
from .models import VistaState

_LOGGER = logging.getLogger(__name__)

# Substrings the keypad's free-text "alpha" field shows while a partition is
# counting down its exit delay. This is the one piece of alpha-text parsing
# this integration does perform -- unlike full zone/bypass-code parsing, it's
# a simple, stable substring check with no panel-firmware-dependent heuristic
# behind it.
_EXIT_DELAY_ALPHA_MARKERS = ("you may exit now", "may exit now")

# Ticks (5s each) at or below which a zone is still considered "open" in the
# zone timer dump, per pyenvisalink's own observation: "The envisalink never
# seems to report back exactly 0 seconds for an open zone. It always seems
# to be 1-3 ticks."
_OPEN_ZONE_TICK_THRESHOLD = 3


def _decode_icon_flags(icon_led_hex: str) -> dict[str, bool]:
    value = int(icon_led_hex, 16)
    return {name: bool(value & (1 << bit)) for name, bit in ICON_LED_BITS.items()}


def invalid_keypad_field(event: TPIEvent) -> tuple[str, int] | None:
    """Name the first malformed field without exposing any wire content."""
    fields = event.fields
    checks = (
        ("partition", r"0?[1-8]"),
        ("icon_led_hex", r"[0-9A-Fa-f]{4}"),
        ("zone_or_beep_field", r"(?:0|[0-9]{2,3})"),
        ("beep_hex", r"[0-9A-Fa-f]{2}"),
        ("alpha", r"[\x20-\x7e]{1,32}"),
    )
    for name, pattern in checks:
        value = fields.get(name)
        if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
            return name, len(value) if isinstance(value, str) else 0
    return None


def valid_keypad_update(event: TPIEvent) -> bool:
    """Accept a %00 only when every field has its expected wire shape."""
    return invalid_keypad_field(event) is None


def _arm_state_from_flags(
    armed_away: bool, armed_stay: bool, zero_entry_delay: bool
) -> str:
    if armed_stay and zero_entry_delay:
        return "armed_night"
    if armed_away:
        return "armed_away"
    if armed_stay:
        return "armed_home"
    return "disarmed"


def _apply_keypad_update(state: VistaState, event: TPIEvent) -> None:
    if not valid_keypad_update(event):
        return
    try:
        partition_number = int(event.fields["partition"])
    except KeyError, ValueError:
        return

    partition = state.partitions.get(partition_number)
    if partition is None:
        # Nothing here tracks it, so nothing may act on what it says.
        _LOGGER.debug("Keypad update for untracked partition %s", partition_number)
        return
    flags = _decode_icon_flags(str(event.fields.get("icon_led_hex", "")))
    alpha = str(event.fields.get("alpha", ""))

    partition.fresh = True
    partition.ready = flags["ready"]
    partition.alarm = flags["alarm"]
    partition.alarm_in_memory = flags["alarm_in_memory"]
    partition.alarm_fire_zone = flags["alarm_fire_zone"]
    partition.fire = flags["fire"]
    partition.chime_enabled = flags["chime"]
    partition.ac_present = flags["ac_present"]
    partition.low_battery = flags["low_battery"]
    partition.trouble = flags["system_trouble"]
    alpha_lower = alpha.lower()
    partition.exit_delay = any(
        marker in alpha_lower for marker in _EXIT_DELAY_ALPHA_MARKERS
    )

    was_bypass_active = partition.bypass_active
    partition.bypass_active = flags["bypass"]
    if was_bypass_active and not partition.bypass_active:
        for zone in state.zones.values():
            if zone.partition == partition_number:
                zone.bypassed = False

    armed_away = flags["armed_away"]
    armed_stay = flags["armed_stay"]
    zero_entry_delay = flags["armed_zero_entry_delay"]
    partition.armed = armed_away or armed_stay
    partition.arm_state = _arm_state_from_flags(
        armed_away, armed_stay, zero_entry_delay
    )


class ProgramModeReport(Enum):
    """What one event says about Program Mode, for the coordinator to store."""

    OPENED = "opened"
    CLOSED = "closed"
    # A tracked partition reported armed.
    ARMED = "armed"


def program_mode_report(
    event: TPIEvent, num_partitions: int
) -> ProgramModeReport | None:
    """CID 627 and 628, or an armed keypad update from a partition 1..num_partitions."""
    if event.code == EVT_REALTIME_CID_EVENT:
        try:
            cid_event = int(event.fields["cid_event"])
        except KeyError, ValueError:
            return None
        if cid_event == INSTALLERS_MODE_CID_EVENT:
            return ProgramModeReport.OPENED
        if cid_event == INSTALLERS_MODE_EXIT_CID_EVENT:
            return ProgramModeReport.CLOSED
        return None
    if event.code != EVT_KEYPAD_UPDATE:
        return None
    if not valid_keypad_update(event):
        return None
    try:
        partition_number = int(event.fields["partition"])
    except KeyError, ValueError:
        return None
    if not 1 <= partition_number <= num_partitions:
        return None
    flags = _decode_icon_flags(str(event.fields.get("icon_led_hex", "")))
    if flags["armed_away"] or flags["armed_stay"]:
        return ProgramModeReport.ARMED
    return None


def _apply_realtime_cid_event(state: VistaState, event: TPIEvent) -> None:
    try:
        cid_event = int(event.fields["cid_event"])
    except KeyError, ValueError:
        return

    if cid_event not in ARM_DISARM_CID_EVENTS:
        return

    qualifier = event.fields.get("qualifier")
    try:
        partition_number = int(event.fields.get("partition", "1")) or 1
    except ValueError:
        partition_number = 1
    zone_or_user = str(event.fields.get("zone_or_user", ""))

    partition = state.partitions.get(partition_number)
    if partition is None:
        return
    if qualifier == CID_QUALIFIER_OPENING:
        partition.last_disarmed_by_user = zone_or_user
    elif qualifier == CID_QUALIFIER_CLOSING:
        partition.last_armed_by_user = zone_or_user


def _apply_zone_timer_dump(state: VistaState, event: TPIEvent) -> None:
    hex_string = event.raw_data
    for zone_number in range(1, len(hex_string) // 4 + 1):
        if zone_number not in state.zones:
            continue
        chunk = hex_string[(zone_number - 1) * 4 : zone_number * 4]
        if len(chunk) != 4:
            continue
        try:
            # Little-endian: swap the two byte-pairs before parsing as hex.
            raw_value = int(chunk[2:4] + chunk[0:2], 16)
        except ValueError:
            continue
        ticks = 0xFFFF - raw_value
        zone = state.zone(zone_number)
        zone.open = ticks <= _OPEN_ZONE_TICK_THRESHOLD
        zone.seconds_since_fault = ticks * 5


def apply_event(state: VistaState, event: TPIEvent) -> None:
    """Mutate ``state`` in place to reflect ``event``. Unknown codes are ignored."""
    if event.code == EVT_KEYPAD_UPDATE:
        _apply_keypad_update(state, event)
    elif event.code == EVT_REALTIME_CID_EVENT:
        _apply_realtime_cid_event(state, event)
    elif event.code == EVT_ZONE_TIMER_DUMP:
        _apply_zone_timer_dump(state, event)
    # %01/%02 (zone/partition state change), %20 (debug), and ^xx command
    # acknowledgements have no state effect for a Honeywell panel over this
    # protocol; the coordinator still surfaces them via last_event for
    # diagnostics.
