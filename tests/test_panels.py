"""Tests for the panel-model + dialect abstraction (pure logic, no HA).

Covers the registry lookup, both family dialects' Program-Mode grammar and
installer-mode detection, and the honesty invariants (verification levels,
which family supports guided per-zone programming).
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
from custom_components.envisalink_field_programmer.panels.dsc import DSC_DIALECT
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
    assert get_model("pc1864").model_id == "dsc_pc1864"  # DSC alias


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


# --- DSC dialect ----------------------------------------------------------

def test_dsc_dialect_family_and_no_guided_support():
    assert DSC_DIALECT.family == PanelFamily.DSC_POWERSERIES
    # DSC uses positional whole-section programming; the VISTA-shaped guided
    # per-zone flow deliberately does not drive it.
    assert DSC_DIALECT.supports_guided_field_programming is False
    assert DSC_DIALECT.guided_field_programming_note


def test_dsc_program_mode_wrapper():
    assert DSC_DIALECT.program_mode_wrapper("5555", "001") == "*85555001##"


def test_dsc_opens_program_mode_detects_star_8_code():
    assert DSC_DIALECT.opens_program_mode("*85555001", "5555") is True
    assert DSC_DIALECT.opens_program_mode("*89999", None) is True  # generic
    # VISTA's <code>800 is NOT how DSC opens programming.
    assert DSC_DIALECT.opens_program_mode("4112800*56", None) is False


def test_dsc_zone_types_flag_fire_and_co():
    codes = DSC_DIALECT.life_safety_zone_codes()
    assert 9 in codes  # 24-hour fire
    assert 13 in codes  # CO
    assert 3 not in codes  # instant/perimeter


def test_all_dsc_models_are_provisional():
    dsc = [m for m in MODELS if m.family == PanelFamily.DSC_POWERSERIES]
    assert dsc  # there are some
    assert all(m.verification == Verification.PROVISIONAL for m in dsc)


# --- guard is family-aware ------------------------------------------------

def test_guard_blocks_dsc_program_mode_only_under_dsc_dialect():
    # Under the DSC dialect, *8<code> is refused...
    with pytest.raises(KeystrokeGuardError):
        validate_keystrokes("*85555001", dialect=DSC_DIALECT)
    # ...but the same string under the (default) VISTA dialect is not, because
    # Vista has no *8 installer menu at all.
    validate_keystrokes("*85555001")  # must not raise


def test_guard_blocks_vista_program_mode_only_under_vista_dialect():
    # Vista's <code>800 is refused under Vista...
    with pytest.raises(KeystrokeGuardError):
        validate_keystrokes("4112800*56", dialect=VISTA_DIALECT)
    # ...but is not the DSC trigger, so DSC's guard leaves it alone.
    validate_keystrokes("4112800*56", dialect=DSC_DIALECT)  # must not raise
