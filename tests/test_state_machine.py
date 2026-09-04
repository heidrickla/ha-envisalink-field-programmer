"""Tests for folding TPIEvents into VistaState.

Icon-LED hex values below are built by hand from ICON_LED_BITS so each
scenario documents exactly which flags are set. See const.py for the bit
assignments and client.py/state_machine.py module docstrings for how this
maps to a real keypad update.
"""

from __future__ import annotations

from custom_components.envisalink_field_programmer.client import build_event
from custom_components.envisalink_field_programmer.const import ICON_LED_BITS
from custom_components.envisalink_field_programmer.models import VistaState
from custom_components.envisalink_field_programmer.state_machine import apply_event


def _state(num_zones: int = 4) -> VistaState:
    return VistaState.create(num_partitions=2, num_zones=num_zones)


def _icon_hex(*flags: str) -> str:
    value = 0
    for flag in flags:
        value |= 1 << ICON_LED_BITS[flag]
    return f"{value:x}"


def _keypad_update(partition: int, *flags: str, alpha: str = ""):
    return build_event("%00", f"{partition},{_icon_hex(*flags)},0,00,{alpha}")


def test_ready_idle_partition():
    state = _state()
    apply_event(state, _keypad_update(1, "ready", "ac_present", alpha="READY"))
    partition = state.partition(1)
    assert partition.ready is True
    assert partition.ac_present is True
    assert partition.armed is False
    assert partition.arm_state == "disarmed"


def test_armed_away():
    state = _state()
    apply_event(state, _keypad_update(1, "armed_away", "ac_present", alpha="ARMED AWAY"))
    partition = state.partition(1)
    assert partition.armed is True
    assert partition.arm_state == "armed_away"


def test_armed_stay_with_zero_entry_delay_is_armed_night():
    state = _state()
    apply_event(
        state,
        _keypad_update(1, "armed_stay", "armed_zero_entry_delay", "ac_present"),
    )
    partition = state.partition(1)
    assert partition.armed is True
    assert partition.arm_state == "armed_night"


def test_armed_stay_alone_is_armed_home():
    state = _state()
    apply_event(state, _keypad_update(1, "armed_stay", "ac_present"))
    assert state.partition(1).arm_state == "armed_home"


def test_alarm_flag():
    state = _state()
    apply_event(state, _keypad_update(1, "alarm"))
    assert state.partition(1).alarm is True


def test_exit_delay_detected_from_alpha_text():
    state = _state()
    apply_event(state, _keypad_update(1, alpha="You may exit now"))
    assert state.partition(1).exit_delay is True

    apply_event(state, _keypad_update(1, "ready", alpha="READY"))
    assert state.partition(1).exit_delay is False


def test_bypass_active_clears_zone_bypass_flags_for_partition():
    state = _state()
    apply_event(state, _keypad_update(1, "bypass", "ac_present", alpha="BYPASS"))
    assert state.partition(1).bypass_active is True

    # Simulate the coordinator's optimistic bypass tracking having marked a
    # zone bypassed earlier.
    zone = state.zone(1)
    zone.partition = 1
    zone.bypassed = True

    apply_event(state, _keypad_update(1, "ac_present", alpha="READY"))
    assert state.partition(1).bypass_active is False
    assert state.zone(1).bypassed is False


def test_zone_timer_dump_marks_recently_faulted_zones_open():
    state = _state()
    # Wire bytes are little-endian; FEFF -> raw 0xFFFE -> 1 tick -> open.
    # 0000 -> raw 0x0000 -> 65535 ticks -> closed.
    hex_string = "FEFF" + "0000" + "FEFF" + "0000"
    apply_event(state, build_event("%FF", hex_string))

    assert state.zone(1).open is True
    assert state.zone(1).seconds_since_fault == 5
    assert state.zone(2).open is False
    assert state.zone(3).open is True
    assert state.zone(4).open is False


def test_installers_mode_flag_set_and_cleared_via_cid_event():
    state = _state()
    # qualifier(1) + cid_event(627, Program Mode Entry) + partition(01) + zone_or_user(000)
    apply_event(state, build_event("%03", "1" + "627" + "01" + "000"))
    assert state.system.installers_mode is True

    apply_event(state, build_event("%03", "1" + "628" + "01" + "000"))
    assert state.system.installers_mode is False


def test_arm_disarm_cid_event_tracks_last_user():
    state = _state()
    # qualifier=3 (closing/arm), cid_event=401 (an arm/disarm CID code),
    # partition=01, user=005.
    apply_event(state, build_event("%03", "3" + "401" + "01" + "005"))
    assert state.partition(1).last_armed_by_user == "005"

    # qualifier=1 (opening/disarm)
    apply_event(state, build_event("%03", "1" + "401" + "01" + "005"))
    assert state.partition(1).last_disarmed_by_user == "005"
    assert state.partition(1).last_user == "005"


def test_unknown_event_is_ignored_without_error():
    state = _state()
    apply_event(state, build_event("%20", "whatever"))  # must not raise


def test_zone_state_and_partition_state_change_are_noops():
    state = _state()
    apply_event(state, build_event("%01", "0000000000000000"))
    apply_event(state, build_event("%02", "1"))  # must not raise, no effect
