"""Tests for the field-programming keystroke translation layer.

Pure logic, no HA/asyncio required. Verifies the keystroke sequences built
from structured (validated) input match the *56/*57/numbered-field
conventions documented in the Vista programming guide.
"""

from __future__ import annotations

import pytest

from custom_components.envisalink_field_programmer.field_programming import (
    LIFE_SAFETY_ZONE_TYPE_CODES,
    FunctionKeyAction,
    FunctionKeyLetter,
    HardwireType,
    ResponseTime,
    SystemTimingField,
    ZoneProgram,
    build_function_key_keystrokes,
    build_program_mode_wrapper,
    build_system_timing_keystrokes,
    build_zone_program_keystrokes,
)


def test_zone_program_rejects_invalid_zone_number():
    with pytest.raises(ValueError):
        ZoneProgram(zone_number=0, zone_type=3, partition=1)
    with pytest.raises(ValueError):
        ZoneProgram(zone_number=65, zone_type=3, partition=1)


def test_zone_program_rejects_unknown_zone_type():
    with pytest.raises(ValueError):
        ZoneProgram(zone_number=1, zone_type=999, partition=1)


def test_zone_program_rejects_invalid_partition():
    with pytest.raises(ValueError):
        ZoneProgram(zone_number=1, zone_type=3, partition=4)


def test_life_safety_codes_include_fire_and_co():
    assert 9 in LIFE_SAFETY_ZONE_TYPE_CODES  # Fire
    assert 16 in LIFE_SAFETY_ZONE_TYPE_CODES  # Fire w/ verification
    assert 14 in LIFE_SAFETY_ZONE_TYPE_CODES  # CO
    assert 3 not in LIFE_SAFETY_ZONE_TYPE_CODES  # Perimeter is not life-safety


def test_build_zone_program_keystrokes_zone_1_perimeter():
    program = ZoneProgram(
        zone_number=1,
        zone_type=3,
        partition=1,
        report_enabled=True,
        response_time=ResponseTime.MS_350,
    )
    keys = build_zone_program_keystrokes(program)
    # Zone 1 never gets a HARDWIRE TYPE prompt (always EOL per the guide).
    assert keys == "*560*01**03*1*1*1*0*00*"


def test_build_zone_program_keystrokes_zone_5_gets_hardwire_prompt():
    program = ZoneProgram(
        zone_number=5,
        zone_type=9,  # Fire
        partition=1,
        report_enabled=True,
        hardwire_type=HardwireType.DOUBLE_BALANCED,
        response_time=ResponseTime.SEC_1_2,
    )
    keys = build_zone_program_keystrokes(program)
    assert "05" in keys
    assert keys.startswith("*560*05**09*1*1*")
    # hardwire type (4 = double-balanced) then response time (3 = 1.2s)
    assert "4*3*" in keys


def test_build_zone_program_keystrokes_zone_9_uses_input_type_not_hardwire():
    program = ZoneProgram(zone_number=9, zone_type=3, partition=2)
    keys = build_zone_program_keystrokes(program)
    assert not program.is_hardwired_prompt_zone
    # "2*" for INPUT TYPE (aux wired) appears instead of a response-time digit
    assert keys.endswith("2*0*00*")


def test_build_zone_program_keystrokes_report_disabled():
    program = ZoneProgram(zone_number=1, zone_type=0, partition=1, report_enabled=False)
    keys = build_zone_program_keystrokes(program)
    assert "00*" in keys  # report code disabled


def test_build_system_timing_exit_delay_in_range():
    assert build_system_timing_keystrokes(SystemTimingField.EXIT_DELAY, 45) == "*3445*"


def test_build_system_timing_exit_delay_special_value():
    assert build_system_timing_keystrokes(SystemTimingField.EXIT_DELAY, 97) == "*3497*"


def test_build_system_timing_exit_delay_out_of_range_rejected():
    with pytest.raises(ValueError):
        build_system_timing_keystrokes(SystemTimingField.EXIT_DELAY, 200)


def test_build_system_timing_entry_delay_allows_extended_specials():
    assert build_system_timing_keystrokes(SystemTimingField.ENTRY_DELAY_1, 99) == "*3599*"


def test_build_system_timing_auto_stay_arm_valid_values():
    for value in (0, 1, 2, 3):
        assert build_system_timing_keystrokes(SystemTimingField.AUTO_STAY_ARM, value) == (
            f"*84{value}"
        )


def test_build_system_timing_auto_stay_arm_rejects_invalid():
    with pytest.raises(ValueError):
        build_system_timing_keystrokes(SystemTimingField.AUTO_STAY_ARM, 9)


def test_build_function_key_keystrokes():
    keys = build_function_key_keystrokes(
        FunctionKeyLetter.A, partition=1, action=FunctionKeyAction.ARM_AWAY
    )
    assert keys == "*571*1*03*0*00"


def test_build_function_key_keystrokes_rejects_bad_partition():
    with pytest.raises(ValueError):
        build_function_key_keystrokes(
            FunctionKeyLetter.B, partition=9, action=FunctionKeyAction.ARM_STAY
        )


def test_build_program_mode_wrapper_uses_normal_exit_never_lockout():
    wrapped = build_program_mode_wrapper("4112", "*56...")
    assert wrapped == "4112800*56...*99"
    assert "*98" not in wrapped
