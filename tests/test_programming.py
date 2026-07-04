"""Tests for the keystroke safety guard in programming.py.

This is the most safety-critical piece of the whole integration: it is the
only thing standing between a careless automation and an accidental
installer-mode lockout. Every branch is tested explicitly.
"""
from __future__ import annotations

import pytest

from custom_components.vista_console.programming import (
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


def test_installer_mode_sequence_blocked_by_default():
    with pytest.raises(KeystrokeGuardError, match="installer"):
        validate_keystrokes("*81234")


def test_installer_mode_sequence_allowed_when_confirmed():
    validate_keystrokes("*81234", allow_installer_mode=True)  # must not raise


def test_installer_trigger_blocked_even_mid_sequence():
    with pytest.raises(KeystrokeGuardError):
        validate_keystrokes("1*82")
