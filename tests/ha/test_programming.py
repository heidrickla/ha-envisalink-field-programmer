"""Tests for the keystroke safety guard in programming.py.

This is the most safety-critical piece of the whole integration: it is the
only thing standing between a careless automation and accidentally opening
full installer Program Mode. Every branch is tested explicitly.

Note: Program Mode on a real Vista panel opens via
``<installer code>800`` (e.g. "4112800" with the factory-default code), not
a DSC-style "*8" sequence -- see programming.py's module docstring for why
that distinction matters and was corrected.
"""

from __future__ import annotations

import pytest

from custom_components.envisalink_field_programmer.programming import (
    KeystrokeGuardError,
    validate_keystrokes,
)


def test_ordinary_zone_bypass_sequence_is_allowed():
    validate_keystrokes("*101#")  # must not raise


def test_empty_keys_rejected():
    with pytest.raises(KeystrokeGuardError):
        validate_keystrokes("")


def test_invalid_characters_rejected():
    with pytest.raises(KeystrokeGuardError):
        validate_keystrokes("12A34")


_GUIDED_FUNCTION_KEY = "4112800*57A*1*03*0**99"
_BOTH = {"allow_installer_mode": True, "allow_function_key": True}


def test_function_key_letter_passes_at_the_57_prompt_in_program_mode():
    validate_keystrokes(_GUIDED_FUNCTION_KEY, **_BOTH)  # must not raise


@pytest.mark.parametrize(
    ("keys", "flags"),
    [
        (_GUIDED_FUNCTION_KEY, {"allow_installer_mode": True}),
        (_GUIDED_FUNCTION_KEY, {"allow_function_key": True}),
        ("4112800*56A*", _BOTH),
        ("*57A*1*03*0**99", _BOTH),
        ("4112800*57A*1*03*0*57B*", _BOTH),
        ("A", _BOTH),
    ],
    ids=[
        "function key not allowed",
        "installer mode not allowed",
        "not at the *57 prompt",
        "Program Mode not opened",
        "two letters",
        "bare panic letter",
    ],
)
def test_function_key_letter_refused_anywhere_else(keys, flags):
    with pytest.raises(KeystrokeGuardError) as exc:
        validate_keystrokes(keys, **flags)
    assert exc.value.translation_key == "invalid_keystroke_characters"


def test_program_mode_sequence_blocked_with_known_installer_code():
    with pytest.raises(KeystrokeGuardError) as exc:
        validate_keystrokes("4112800*56", installer_code="4112")
    assert exc.value.translation_key == "opens_program_mode"


def test_program_mode_error_redacts_the_installer_code():
    # The refused sequence is a translation placeholder, so it reaches the HA
    # logs, the error toast and the programming result sensor as part of the
    # message: it must not leak the installer/user code embedded in the
    # keystrokes. Runs of 4+ digits are masked; the *56/*99 operators are kept
    # for context.
    with pytest.raises(KeystrokeGuardError) as exc:
        validate_keystrokes("4112800*56", installer_code="4112")
    keys = exc.value.translation_placeholders["keys"]
    assert "4112" not in keys
    assert "4112800" not in keys
    assert "[code]" in keys
    assert "*56" in keys  # non-secret operator preserved for debuggability


def test_program_mode_sequence_allowed_when_confirmed():
    validate_keystrokes(
        "4112800*56", installer_code="4112", allow_installer_mode=True
    )  # must not raise


def test_program_mode_blocked_by_generic_pattern_without_known_code():
    # Even without a configured installer_code, a run of 4-6 digits
    # immediately followed by "800" is exactly what opening Program Mode
    # looks like on the wire, regardless of which code is in use.
    with pytest.raises(KeystrokeGuardError) as exc:
        validate_keystrokes("9876800*56")
    assert exc.value.translation_key == "opens_program_mode"


def test_unrelated_800_substring_is_not_flagged_without_a_preceding_code_run():
    # A bare "800" with no immediately-preceding 4-6 digit run must not be
    # treated as Program Mode entry -- e.g. plausible inside a longer
    # keystroke sequence for something unrelated.
    validate_keystrokes("*800#")  # must not raise


def test_old_dsc_style_star_8_sequence_is_not_flagged():
    # Vista has no "*8" menu, so a "*8" substring is not installer-mode entry
    # by itself and the guard must not block it.
    validate_keystrokes("*81234")  # must not raise
