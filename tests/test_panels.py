"""Tests for the panel-model + dialect abstraction (pure logic, no HA).

Covers the registry lookup, the VISTA family dialect's Program-Mode grammar
and installer-mode detection, and the honesty invariants (verification levels,
which family supports guided per-zone programming). DSC-family cases are added
alongside the DSC dialect.
"""
from __future__ import annotations

import pytest

from custom_components.envisalink_field_programmer.panels import (
    DEFAULT_MODEL_ID,
    MODELS,
    PanelFamily,
    Verification,
    get_dialect,
    get_model,
    model_choices,
)
from custom_components.envisalink_field_programmer.panels.vista import VISTA_DIALECT
from custom_components.envisalink_field_programmer.programming import (
    KeystrokeGuardError,
    validate_keystrokes,
)

# --- registry -------------------------------------------------------------

def test_default_model_is_vista_21ip_and_verified():
    model = get_model(None)
    assert model.model_id == DEFAULT_MODEL_ID == "vista_21ip"
    assert model.verification == Verification.VERIFIED


def test_get_model_resolves_canonical_alias_and_normalized():
    assert get_model("vista_20p").model_id == "vista_20p"
    assert get_model("20p").model_id == "vista_20p"  # alias
    assert get_model("VISTA-20P").model_id == "vista_20p"  # normalized


def test_get_model_unknown_raises():
    with pytest.raises(KeyError):
        get_model("totally_made_up_panel")


def test_every_model_maps_to_a_dialect_of_its_own_family():
    for model in MODELS:
        assert get_dialect(model.model_id).family == model.family


def test_model_choices_covers_all_models():
    choices = model_choices()
    assert len(choices) == len(MODELS)
    assert choices["vista_21ip"] == "Honeywell VISTA-21iP"


def test_only_vista_21ip_is_fully_verified():
    verified = [m for m in MODELS if m.verification == Verification.VERIFIED]
    assert [m.model_id for m in verified] == ["vista_21ip"]


# --- VISTA dialect --------------------------------------------------------

def test_vista_dialect_family_and_guided_support():
    assert VISTA_DIALECT.family == PanelFamily.VISTA
    assert VISTA_DIALECT.supports_guided_field_programming is True


def test_vista_program_mode_wrapper():
    assert VISTA_DIALECT.program_mode_wrapper("4112", "*56X") == "4112800*56X*99"


def test_vista_opens_program_mode_detects_800():
    assert VISTA_DIALECT.opens_program_mode("4112800*56", "4112") is True
    assert VISTA_DIALECT.opens_program_mode("9876800", None) is True  # generic
    assert VISTA_DIALECT.opens_program_mode("*85555", None) is False  # DSC-style


def test_vista_zone_types_flag_life_safety():
    codes = VISTA_DIALECT.life_safety_zone_codes()
    assert 9 in codes and 14 in codes and 16 in codes
    assert 3 not in codes


# --- guard is family-aware (Vista side) -----------------------------------

def test_guard_blocks_vista_program_mode_under_vista_dialect():
    with pytest.raises(KeystrokeGuardError):
        validate_keystrokes("4112800*56", dialect=VISTA_DIALECT)


def test_guard_leaves_dsc_style_star8_alone_under_vista():
    # Vista has no *8 installer menu at all, so a *8... sequence must not be
    # treated as installer-mode entry by the (default) Vista guard.
    validate_keystrokes("*85555001")  # must not raise
