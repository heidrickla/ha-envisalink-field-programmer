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


def test_verified_models_are_the_guide_checked_residential_vistas():
    # The residential VISTA line, each cross-checked field-by-field against its
    # own programming guide (2026-07-05): 21iP (K14488PRV3), 20P/15P
    # (v15pand20pprogrammingguide), 10P (vista10pprogramming). Everything else
    # remains inherited/provisional until checked against its own guide.
    verified = {m.model_id for m in MODELS if m.verification == Verification.VERIFIED}
    assert verified == {"vista_21ip", "vista_20p", "vista_15p", "vista_10p"}


# --- VISTA dialect --------------------------------------------------------


def test_vista_dialect_family_and_guided_support():
    from custom_components.envisalink_field_programmer.panels import GuidedOp

    assert VISTA_DIALECT.family == PanelFamily.VISTA
    # Residential VISTA drives all three guided operations.
    assert VISTA_DIALECT.supported_guided_ops == frozenset(
        {GuidedOp.ZONE, GuidedOp.TIMING, GuidedOp.FUNCTION_KEY}
    )


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


def test_vista_residential_timing_builder():
    # Residential timing is system-wide (partition ignored) -- same output as
    # the underlying field_programming builder: exit delay (34) = 45 seconds.
    assert VISTA_DIALECT.build_timing_keystrokes("34", 45, partition=1) == "*3445*"


# --- Commercial VISTA dialect ---------------------------------------------


def test_commercial_vista_dialect_supports_timing_only():
    from custom_components.envisalink_field_programmer.panels import GuidedOp, get_dialect

    dialect = get_dialect("vista_128bp")
    assert dialect.supported_guided_ops == frozenset({GuidedOp.TIMING})
    # 250BP shares the same commercial dialect.
    assert get_dialect("vista_250bp") is dialect


def test_commercial_vista_program_mode_uses_8000():
    from custom_components.envisalink_field_programmer.panels import get_dialect

    dialect = get_dialect("vista_128bp")
    assert dialect.program_mode_wrapper("1234", "X") == "12348000X*99"
    assert dialect.opens_program_mode("12348000*0902", "1234") is True
    # Residential <code>800 is not the commercial trigger's full form, but the
    # generic guard still catches any 4-6 digits + 8000.
    assert dialect.opens_program_mode("99998000", None) is True


def test_commercial_vista_timing_builder_partition_specific():
    from custom_components.envisalink_field_programmer.panels import get_dialect

    dialect = get_dialect("vista_128bp")
    # Entry Delay #1 (*09) = 2 units (30s) on partition 1: select partition, edit field.
    assert dialect.build_timing_keystrokes("09", 2, partition=1) == "*911*0902"
    assert dialect.build_timing_keystrokes("12", 15, partition=3) == "*913*1215"


def test_commercial_vista_timing_rejects_out_of_range():
    from custom_components.envisalink_field_programmer.panels import get_dialect

    dialect = get_dialect("vista_128bp")
    for bad in (1, 16, -1):  # valid is 0 or 2-15
        with pytest.raises(ValueError):
            dialect.build_timing_keystrokes("09", bad, partition=1)
    with pytest.raises(ValueError):
        dialect.build_timing_keystrokes("99", 2, partition=1)  # unknown field


# --- DSC dialect ----------------------------------------------------------


def test_dsc_dialect_family_and_no_guided_support():
    assert DSC_DIALECT.family == PanelFamily.DSC_POWERSERIES
    # DSC drives no guided operation yet (no DSC transport).
    assert DSC_DIALECT.supported_guided_ops == frozenset()
    assert DSC_DIALECT.guided_field_programming_note


def test_dsc_program_mode_wrapper():
    assert DSC_DIALECT.program_mode_wrapper("5555", "001") == "*85555001##"


def test_dsc_opens_program_mode_detects_star_8_code():
    assert DSC_DIALECT.opens_program_mode("*85555001", "5555") is True
    assert DSC_DIALECT.opens_program_mode("*89999", None) is True  # generic
    # VISTA's <code>800 is NOT how DSC opens programming.
    assert DSC_DIALECT.opens_program_mode("4112800*56", None) is False


def test_dsc_zone_types_flag_fire_and_co():
    # Real DSC PowerSeries codes (PC1616/1832/1864 guide): [07]/[08] fire,
    # [41]/[81] carbon monoxide are life-safety; [09] is Supervision (not fire).
    codes = DSC_DIALECT.life_safety_zone_codes()
    assert 7 in codes and 8 in codes  # delayed + standard 24-hour fire
    assert 41 in codes and 81 in codes  # CO (hardwired + wireless)
    assert 9 not in codes  # 24-hour supervision, not life-safety
    assert 3 not in codes  # instant/perimeter


def test_all_dsc_models_are_provisional():
    dsc = [m for m in MODELS if m.family == PanelFamily.DSC_POWERSERIES]
    assert dsc  # there are some
    assert all(m.verification == Verification.PROVISIONAL for m in dsc)


# --- DSC section-programming pure builders (not wired to any transport) ----


def test_dsc_zone_definitions_builder():
    from custom_components.envisalink_field_programmer.panels.dsc import (
        build_dsc_zone_definitions,
    )

    # Section 001 (zones 1-8): Delay1, Delay1, Instant, Instant, Interior,
    # Standard-24hr-Fire, Null, Null.
    codes = [1, 1, 3, 3, 4, 8, 0, 0]
    assert build_dsc_zone_definitions(1, codes) == "0010101030304080000"


def test_dsc_zone_definitions_builder_validation():
    from custom_components.envisalink_field_programmer.panels.dsc import (
        build_dsc_zone_definitions,
    )

    with pytest.raises(ValueError):
        build_dsc_zone_definitions(1, [1, 2, 3])  # not 8 codes
    with pytest.raises(ValueError):
        build_dsc_zone_definitions(9, [0] * 8)  # section out of range
    with pytest.raises(ValueError):
        build_dsc_zone_definitions(1, [0, 0, 0, 0, 0, 0, 0, 100])  # code > 99


def test_dsc_partition_timing_builder():
    from custom_components.envisalink_field_programmer.panels.dsc import (
        build_dsc_partition_timing,
    )

    # Partition 1: entry1=30s, entry2=45s, exit=60s.
    assert build_dsc_partition_timing(1, 30, 45, 60) == "00501030045060"


def test_dsc_partition_timing_builder_validation():
    from custom_components.envisalink_field_programmer.panels.dsc import (
        build_dsc_partition_timing,
    )

    with pytest.raises(ValueError):
        build_dsc_partition_timing(1, 0, 45, 60)  # delay < 1
    with pytest.raises(ValueError):
        build_dsc_partition_timing(1, 30, 45, 256)  # delay > 255
    with pytest.raises(ValueError):
        build_dsc_partition_timing(9, 30, 45, 60)  # partition out of range


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


# --- verification-acknowledgment gate -------------------------------------
# Currently every registered model is either fully VERIFIED or has guided
# programming disabled, so no live model trips this gate -- but it must stay
# correct for any future model added as GRAMMAR_VERIFIED/PROVISIONAL *with*
# guided programming enabled. Tested directly against the helper.


def _fake_coordinator(model):
    from types import SimpleNamespace

    return SimpleNamespace(panel_model=model)


def test_verified_or_ack_allows_verified_model_without_ack():
    from custom_components.envisalink_field_programmer.field_programming_services import (
        _require_verified_or_ack,
    )

    model = get_model("vista_21ip")
    assert model.verification == Verification.VERIFIED
    _require_verified_or_ack(_fake_coordinator(model), confirm_unverified=False)  # no raise


def test_verified_or_ack_blocks_unverified_without_ack_and_allows_with():
    from custom_components.envisalink_field_programmer.field_programming_services import (
        _require_verified_or_ack,
    )
    from custom_components.envisalink_field_programmer.panels import PanelModel

    provisional = PanelModel(
        model_id="hypothetical",
        family=PanelFamily.VISTA,
        label="Hypothetical unverified panel",
        max_zones=8,
        max_partitions=1,
        verification=Verification.PROVISIONAL,
        notes="not checked yet",
    )
    with pytest.raises(KeystrokeGuardError, match="not verified"):
        _require_verified_or_ack(_fake_coordinator(provisional), confirm_unverified=False)
    # With the explicit acknowledgment it proceeds.
    _require_verified_or_ack(_fake_coordinator(provisional), confirm_unverified=True)
