"""Tests for folding TPIEvents into VistaState."""
from __future__ import annotations

from custom_components.envisalink_field_programmer.client import build_event
from custom_components.envisalink_field_programmer.models import VistaState
from custom_components.envisalink_field_programmer.state_machine import apply_event


def _state() -> VistaState:
    return VistaState.create(num_partitions=2, num_zones=8)


def test_zone_open_and_restored():
    state = _state()
    apply_event(state, build_event("609", "005"))
    assert state.zone(5).open is True
    apply_event(state, build_event("610", "005"))
    assert state.zone(5).open is False


def test_zone_alarm_sets_partition_from_event():
    state = _state()
    apply_event(state, build_event("601", "2003"))
    zone = state.zone(3)
    assert zone.alarm is True
    assert zone.partition == 2


def test_partition_armed_maps_mode_to_state():
    state = _state()
    apply_event(state, build_event("652", "13"))  # partition 1, mode 3 = zero-entry-stay
    partition = state.partition(1)
    assert partition.armed is True
    assert partition.arm_state == "armed_night"


def test_partition_disarmed_clears_alarm_and_delays():
    state = _state()
    apply_event(state, build_event("654", "1"))
    apply_event(state, build_event("656", "1"))
    partition = state.partition(1)
    assert partition.alarm is True
    assert partition.exit_delay is True

    apply_event(state, build_event("655", "1"))
    assert partition.armed is False
    assert partition.arm_state == "disarmed"
    assert partition.alarm is False
    assert partition.exit_delay is False


def test_installers_mode_flag_set_and_cleared():
    state = _state()
    apply_event(state, build_event("680", ""))
    assert state.system.installers_mode is True

    # Any normal-operation event should clear the flag again (there is no
    # dedicated "left installers mode" event on the wire).
    apply_event(state, build_event("650", "1"))
    assert state.system.installers_mode is False


def test_trouble_flags():
    state = _state()
    apply_event(state, build_event("802", ""))
    assert state.system.ac_trouble is True
    apply_event(state, build_event("803", ""))
    assert state.system.ac_trouble is False


def test_bypass_bitfield_updates_zones():
    state = _state()
    # Byte 0 = 0x05 -> bits 0 and 2 set -> zones 1 and 3 bypassed.
    hex_string = "05" + "00" * 7
    apply_event(state, build_event("616", hex_string))
    assert state.zone(1).bypassed is True
    assert state.zone(2).bypassed is False
    assert state.zone(3).bypassed is True


def test_unknown_event_is_ignored_without_error():
    state = _state()
    apply_event(state, build_event("999", "whatever"))  # must not raise
