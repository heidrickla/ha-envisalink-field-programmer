"""Tests for the field-programming keystroke translation layer.

Pure logic, no HA/asyncio required. Verifies the keystroke sequences built
from structured (validated) input match the *56/*57/numbered-field
conventions documented in the Vista programming guide.
"""

from __future__ import annotations

import pytest

from tests import pure

field_programming = pure.load("field_programming")
LIFE_SAFETY_ZONE_TYPE_CODES = field_programming.LIFE_SAFETY_ZONE_TYPE_CODES
FunctionKeyAction = field_programming.FunctionKeyAction
FunctionKeyLetter = field_programming.FunctionKeyLetter
HardwireType = field_programming.HardwireType
ResponseTime = field_programming.ResponseTime
ProgrammingForm = field_programming.ProgrammingForm
SystemTimingField = field_programming.SystemTimingField
VISTA_10P_ZONES = field_programming.VISTA_10P_ZONES
VISTA_15P_ZONES = field_programming.VISTA_15P_ZONES
VISTA_20P_21IP_ZONES = field_programming.VISTA_20P_21IP_ZONES
ZoneConnection = field_programming.ZoneConnection
ZoneDoubling = field_programming.ZoneDoubling
ZoneProgram = field_programming.ZoneProgram
ZoneRefused = field_programming.ZoneRefused
build_function_key_keystrokes = field_programming.build_function_key_keystrokes
build_program_mode_wrapper = field_programming.build_program_mode_wrapper
build_system_timing_keystrokes = field_programming.build_system_timing_keystrokes
build_zone_program_keystrokes = field_programming.build_zone_program_keystrokes


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


# Zone 3 type 03 (Perimeter) on partition 1 with reporting on reaches the panel
# as: *56, SET TO CONFIRM 0, zone, accept the summary, zone type, partition,
# report code. What follows depends on the zone and the model.
def _prefix_21ip(zone: int) -> str:
    return f"*560*{zone:02d}**03*1*1*"


def _prefix_no_partition(zone: int) -> str:
    return f"*560*{zone:02d}**03*1*"


def _program(zone: int, **overrides):
    values = {
        "zone_number": zone,
        "zone_type": 3,
        "partition": 1,
        "connection": ZoneConnection.WIRED_EXPANDER,
    }
    values.update(overrides)
    return ZoneProgram(**values)


def _refusal(layout, program, doubling) -> str:
    with pytest.raises(ZoneRefused) as raised:
        build_zone_program_keystrokes(program, layout, doubling)
    return raised.value.translation_key


BOARD_1 = "1*"  # RESPONSE TIME only: zone 1 is always end-of-line
BOARD = "0*1*"  # HARDWIRE TYPE end-of-line, RESPONSE TIME 350 ms
AUX_WIRED = "2*"  # INPUT TYPE AW
DOUBLED = ""  # the base zone's wiring and response time apply
END = "0*00*"  # PROGRAM ALPHA no, then leave the zone menu

# (zone, doubling not stated, doubling off, doubling on) on the 20P/21iP: the
# tail after the report code, or the refusal's translation key.
VISTA_21IP_TABLE = [
    (1, BOARD_1, BOARD_1, BOARD_1),
    (2, BOARD, BOARD, BOARD),
    (8, BOARD, BOARD, BOARD),
    (
        9,
        "zone_doubling_not_stated",
        AUX_WIRED,
        "zone_unavailable_with_doubling",
    ),
    (10, "zone_doubling_not_stated", AUX_WIRED, DOUBLED),
    (16, "zone_doubling_not_stated", AUX_WIRED, DOUBLED),
    (17, AUX_WIRED, AUX_WIRED, AUX_WIRED),
    (48, AUX_WIRED, AUX_WIRED, AUX_WIRED),
    (49, "zone_is_button", "zone_is_button", "zone_is_button"),
    (64, "zone_is_button", "zone_is_button", "zone_is_button"),
]


@pytest.mark.parametrize(("zone", "not_stated", "off", "on"), VISTA_21IP_TABLE)
def test_vista_21ip_zone_sequences_follow_zone_doubling(zone, not_stated, off, on):
    layout = VISTA_20P_21IP_ZONES
    for doubling, expected in (
        (ZoneDoubling.NOT_STATED, not_stated),
        (ZoneDoubling.OFF, off),
        (ZoneDoubling.ON, on),
    ):
        program = _program(zone)
        if expected.startswith(("zone_", "hardwire_")):
            assert _refusal(layout, program, doubling) == expected, doubling
        else:
            keys = build_zone_program_keystrokes(program, layout, doubling)
            assert keys == _prefix_21ip(zone) + expected + END, doubling


def test_a_doubled_zone_goes_from_report_code_to_program_alpha():
    # A doubled zone with zone doubling on: zone type, partition and report
    # code, then straight to PROGRAM ALPHA.
    keys = build_zone_program_keystrokes(
        _program(12, connection=None), VISTA_20P_21IP_ZONES, ZoneDoubling.ON
    )
    assert keys == "*560*12**03*1*1*0*00*"


def test_a_board_zone_carries_its_wiring_and_response_time():
    program = _program(
        5,
        zone_type=9,
        hardwire_type=HardwireType.DOUBLE_BALANCED,
        response_time=ResponseTime.SEC_1_2,
    )
    keys = build_zone_program_keystrokes(
        program, VISTA_20P_21IP_ZONES, ZoneDoubling.OFF
    )
    assert keys == "*560*05**09*1*1*4*3*0*00*"


def test_reporting_off_sends_00():
    program = _program(1, report_enabled=False)
    keys = build_zone_program_keystrokes(
        program, VISTA_20P_21IP_ZONES, ZoneDoubling.OFF
    )
    assert keys == "*560*01**03*1*00*1*0*00*"


def test_the_partition_is_sent_where_the_menu_asks_for_it():
    program = _program(3, partition=2)
    keys = build_zone_program_keystrokes(
        program, VISTA_20P_21IP_ZONES, ZoneDoubling.OFF
    )
    assert keys == "*560*03**03*2*1*0*1*0*00*"


def test_an_expansion_zone_needs_its_connection_stated():
    layout = VISTA_20P_21IP_ZONES
    assert (
        _refusal(layout, _program(20, connection=None), ZoneDoubling.OFF)
        == "zone_connection_unset"
    )
    assert (
        _refusal(
            layout, _program(20, connection=ZoneConnection.WIRELESS), ZoneDoubling.OFF
        )
        == "zone_is_wireless"
    )


def test_a_doubled_zone_ignores_the_connection():
    for connection in (None, ZoneConnection.WIRELESS):
        keys = build_zone_program_keystrokes(
            _program(10, connection=connection), VISTA_20P_21IP_ZONES, ZoneDoubling.ON
        )
        assert keys == _prefix_21ip(10) + END


def test_zone_doubling_wiring_needs_doubling_stated_on():
    layout = VISTA_20P_21IP_ZONES
    program = _program(5, hardwire_type=HardwireType.ZONE_DOUBLING)
    for doubling in (ZoneDoubling.NOT_STATED, ZoneDoubling.OFF):
        assert _refusal(layout, program, doubling) == "hardwire_zone_doubling_off"
    keys = build_zone_program_keystrokes(program, layout, ZoneDoubling.ON)
    assert keys == _prefix_21ip(5) + "3*1*" + END


def test_zone_doubling_wiring_is_not_checked_where_there_is_no_wiring_prompt():
    # Zone 1 has no HARDWIRE TYPE prompt on the 21iP, so the form's value is
    # never sent and cannot be refused.
    program = _program(1, hardwire_type=HardwireType.ZONE_DOUBLING)
    keys = build_zone_program_keystrokes(
        program, VISTA_20P_21IP_ZONES, ZoneDoubling.OFF
    )
    assert keys == _prefix_21ip(1) + BOARD_1 + END


# (zone, tail or refusal) on the 15P: no PARTITION prompt, zones 1-6, 9-34 and
# 49-56, and no zone doubling whatever the option says.
VISTA_15P_TABLE = [
    (1, BOARD_1),
    (6, BOARD),
    (7, "zone_not_on_panel"),
    (8, "zone_not_on_panel"),
    (9, AUX_WIRED),
    (12, AUX_WIRED),
    (34, AUX_WIRED),
    (35, "zone_not_on_panel"),
    (49, "zone_is_button"),
    (56, "zone_is_button"),
    (57, "zone_not_on_panel"),
]


@pytest.mark.parametrize(("zone", "expected"), VISTA_15P_TABLE)
def test_vista_15p_zone_sequences(zone, expected):
    for doubling in ZoneDoubling:
        program = _program(zone)
        if expected.startswith("zone_"):
            assert _refusal(VISTA_15P_ZONES, program, doubling) == expected
        else:
            keys = build_zone_program_keystrokes(program, VISTA_15P_ZONES, doubling)
            assert keys == _prefix_no_partition(zone) + expected + END


def test_vista_15p_has_no_zone_doubling_or_double_balanced_wiring():
    for wiring in (HardwireType.ZONE_DOUBLING, HardwireType.DOUBLE_BALANCED):
        program = _program(3, hardwire_type=wiring)
        assert (
            _refusal(VISTA_15P_ZONES, program, ZoneDoubling.ON)
            == "hardwire_type_not_on_model"
        )


# The 10P: HARDWIRE TYPE on zones 1-6 including zone 1, no PARTITION prompt,
# and expansion zones 9-24 that are wireless only.
VISTA_10P_TABLE = [
    (1, BOARD),
    (6, BOARD),
    (7, "zone_not_on_panel"),
    (9, "zone_is_wireless"),
    (24, "zone_is_wireless"),
    (25, "zone_not_on_panel"),
    (49, "zone_is_button"),
]


@pytest.mark.parametrize(("zone", "expected"), VISTA_10P_TABLE)
def test_vista_10p_zone_sequences(zone, expected):
    program = _program(zone)
    if expected.startswith("zone_"):
        assert _refusal(VISTA_10P_ZONES, program, ZoneDoubling.OFF) == expected
    else:
        keys = build_zone_program_keystrokes(program, VISTA_10P_ZONES, ZoneDoubling.OFF)
        assert keys == _prefix_no_partition(zone) + expected + END


def test_a_refusal_names_the_zone_and_the_model_s_zones():
    with pytest.raises(ZoneRefused) as raised:
        build_zone_program_keystrokes(_program(7), VISTA_15P_ZONES, ZoneDoubling.OFF)
    assert raised.value.translation_placeholders == {
        "zone": "7",
        "zones": "1-6, 9-34, 49-56",
    }


def test_the_form_spends_the_zone_connection_with_the_confirmations():
    form = ProgrammingForm(zone_connection=ZoneConnection.WIRED_EXPANDER, confirm=True)
    form.clear_confirmations()
    assert form.zone_connection is None
    assert form.confirm is False


def test_build_system_timing_exit_delay_in_range():
    assert build_system_timing_keystrokes(SystemTimingField.EXIT_DELAY, 45) == "*3445*"


def test_build_system_timing_exit_delay_special_value():
    assert build_system_timing_keystrokes(SystemTimingField.EXIT_DELAY, 97) == "*3497*"


def test_build_system_timing_exit_delay_out_of_range_rejected():
    with pytest.raises(ValueError):
        build_system_timing_keystrokes(SystemTimingField.EXIT_DELAY, 200)


def test_build_system_timing_entry_delay_allows_extended_specials():
    assert (
        build_system_timing_keystrokes(SystemTimingField.ENTRY_DELAY_1, 99) == "*3599*"
    )


def test_build_system_timing_auto_stay_arm_valid_values():
    for value in (0, 1, 2, 3):
        assert build_system_timing_keystrokes(
            SystemTimingField.AUTO_STAY_ARM, value
        ) == (f"*84{value}")


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
