"""Honeywell/Ademco VISTA family dialect.

Program-Mode grammar (``<installer code>800`` to open, ``*99`` to exit, ``*56``
zone menu, ``*57`` function-key menu, ``*34``/``*35``/``*36`` timing fields) is
the long-standing, stable convention across the residential VISTA line and is
reused directly from :mod:`field_programming`, which was built strictly from
the VISTA-21iP/21iPSIA Programming Guide (K14488PRV3).

Per-model honesty (see :class:`~.base.Verification`):

  * **VISTA-21iP** -- VERIFIED. This is the panel the whole field-programming
    layer was written and (partially) hardware-tested against (K14488PRV3).
  * **VISTA-20P / 15P** -- VERIFIED (2026-07-05). Cross-checked field-by-field
    against the combined VISTA-15P/20P Programming Guide
    (``v15pand20pprogrammingguide.pdf``): the ``<code>800`` entry, ``*56``/``*57``
    menus, ``*99`` exit, the ``*34``/``*35``/``*36`` timing fields (defaults
    60/30/30) and ``*84`` auto-stay (default 3), and the whole zone-type table
    (00 Not used, 01/02 Entry-exit, 03 Perimeter, 04 Interior Follower, 06/07/08
    24-Hr, 09 Fire, 10 Interior w/Delay, 12 Monitor, 14 CO, 16 Fire w/Verify, 23
    No Alarm Resp, 24 Silent Burglary) are all *identical* to the 21iP. Capacity
    confirmed from the guide: 20P = 48 zones + partitions; 15P = 32 zones
    (1-6, 9-34, 49-56), single partition.
  * **VISTA-10P** -- VERIFIED (2026-07-05) against ``vista10pprogramming.pdf``.
    Program-mode entry, ``*56``/``*57``, ``*99``, the ``*34``/``*35``/``*36``
    timing fields, and the full zone-type table (including 14 Carbon Monoxide)
    are identical to the 21iP. Its zones are 1-6 (hardwired) and 9-24 (RF) with
    no zones 7-8 -- the same shape as the 15P -- so the shared ``*56`` builder is
    correct for every zone that physically exists. Single partition, 22 zones.
    Only cosmetic difference: ``*84`` auto-stay factory default is 1, not 3
    (a default value, not a field-number or keystroke change).
  * **VISTA-128BP / 250BP** -- commercial panels, driven by the separate
    :class:`CommercialVistaDialect` (``dialect_id="vista_commercial"``). Checked
    against the K5894PRV6 guide (2026-07-05): these use a *different* programming
    language -- program mode opens with ``<code>8000`` (not ``<code>800``), zones
    are programmed through the conditional ``#93`` menu (not ``*56``), and
    entry/exit timing lives in partition-specific fields ``*09``-``*12`` in
    15-second units. Guided **timing** *is* driven (those are simple data-field
    edits); guided **zone** programming is not (the ``#93`` flow is too
    conditional to drive blind, without hardware). Kept PROVISIONAL -- the
    timing builder is guide-derived, not hardware-confirmed.
"""

from __future__ import annotations

from ..field_programming import (
    LIFE_SAFETY_ZONE_TYPE_CODES,
    SYSTEM_TIMING_DESCRIPTIONS,
    SYSTEM_TIMING_LABELS,
    ZONE_TYPES,
    SystemTimingField,
    build_program_mode_wrapper,
    build_system_timing_keystrokes,
)
from .base import (
    GuidedOp,
    PanelDialect,
    PanelFamily,
    PanelModel,
    TimingFieldDef,
    Verification,
    ZoneTypeDef,
)

# Reuse the verified residential zone-type table, projected onto the
# family-agnostic ZoneTypeDef shape the dialect protocol speaks in.
_VISTA_ZONE_TYPES: dict[int, ZoneTypeDef] = {
    code: ZoneTypeDef(
        code=zt.code,
        label=zt.label,
        description=zt.description,
        life_safety=zt.life_safety,
    )
    for code, zt in ZONE_TYPES.items()
}


def _vista_opens_program_mode(keys: str, installer_code: str | None, suffix: str) -> bool:
    """Shared VISTA Program-Mode detector for a given entry suffix (800/8000)."""
    import re

    if installer_code and f"{installer_code}{suffix}" in keys:
        return True
    return bool(re.search(rf"\d{{4,6}}{suffix}", keys))


class VistaDialect:
    """Residential VISTA dialect (21iP/20P/15P/10P): ``*56`` / ``<code>800``."""

    family = PanelFamily.VISTA
    supported_guided_ops = frozenset({GuidedOp.ZONE, GuidedOp.TIMING, GuidedOp.FUNCTION_KEY})
    guided_field_programming_note = (
        "Residential VISTA *56 zone programming, *34/*35/*36 timing, and *57 "
        "function keys are all wired into the guided flow."
    )

    def zone_types(self) -> dict[int, ZoneTypeDef]:
        return _VISTA_ZONE_TYPES

    def life_safety_zone_codes(self) -> frozenset[int]:
        return LIFE_SAFETY_ZONE_TYPE_CODES

    def program_mode_wrapper(self, installer_code: str, action_keystrokes: str) -> str:
        return build_program_mode_wrapper(installer_code, action_keystrokes)

    def opens_program_mode(self, keys: str, installer_code: str | None) -> bool:
        return _vista_opens_program_mode(keys, installer_code, "800")

    def timing_fields(self) -> dict[str, TimingFieldDef]:
        return {
            f.value: TimingFieldDef(
                key=f.value,
                label=SYSTEM_TIMING_LABELS[f],
                description=SYSTEM_TIMING_DESCRIPTIONS.get(f, ""),
                partition_specific=False,  # residential timing is system-wide
            )
            for f in SystemTimingField
        }

    def build_timing_keystrokes(self, field_key: str, value: int, partition: int) -> str:
        # Residential timing is system-wide; partition is ignored.
        return build_system_timing_keystrokes(SystemTimingField(field_key), value)


VISTA_DIALECT: PanelDialect = VistaDialect()


# --- Commercial VISTA (128BP/250BP) ---------------------------------------
# Zone-type reference from the VISTA-128BP/250BP #93 menu (K5894PRV6). A curated
# subset like the residential table -- omits the wireless-pushbutton arm/disarm
# types (20/21/22), access-point (27), and supervisory types (12/28/29).
_COMMERCIAL_VISTA_ZONE_TYPES: dict[int, ZoneTypeDef] = {
    0: ZoneTypeDef(0, "Unused", "No zone assigned."),
    1: ZoneTypeDef(1, "Entry/Exit #1 (burglary)", "Main entry door; entry/exit delay #1."),
    2: ZoneTypeDef(2, "Entry/Exit #2 (burglary)", "Secondary entry door; entry/exit delay #2."),
    3: ZoneTypeDef(3, "Perimeter (burglary)", "Exterior door/window; instant alarm when armed."),
    4: ZoneTypeDef(
        4, "Interior Follower (burglary)", "Interior zone; delayed only after an entry door."
    ),
    5: ZoneTypeDef(5, "Trouble Day / Alarm Night", "Trouble by day, alarm when armed at night."),
    6: ZoneTypeDef(6, "24-Hour Silent Alarm", "Silent report to the monitoring station."),
    7: ZoneTypeDef(7, "24-Hour Audible Alarm", "Audible alarm + report, always active."),
    8: ZoneTypeDef(
        8, "24-Hour Auxiliary", "Aux emergency/monitoring zone; keypad beeps, no siren."
    ),
    9: ZoneTypeDef(
        9,
        "Fire Without Verification",
        "Hardwired smoke/heat detector; always active, cannot be bypassed. Life safety.",
        life_safety=True,
    ),
    10: ZoneTypeDef(
        10,
        "Interior Delay (burglary)",
        "Interior zone that always gets entry delay when armed Away.",
    ),
    14: ZoneTypeDef(
        14, "Carbon Monoxide Detector", "CO detector, always active. Life safety.", life_safety=True
    ),
    16: ZoneTypeDef(
        16,
        "Fire With Verification",
        "Smoke/heat detector with alarm verification. Always active. Life safety.",
        life_safety=True,
    ),
    23: ZoneTypeDef(23, "No Alarm Response", "No security response (e.g. relay-trigger only)."),
}

_COMMERCIAL_LIFE_SAFETY = frozenset(
    c for c, zt in _COMMERCIAL_VISTA_ZONE_TYPES.items() if zt.life_safety
)

# Commercial entry/exit timing data fields (*09-*12), partition-specific, in
# units of 15 seconds (value 00, or 02-15). Verified against K5894PRV6.
_COMMERCIAL_TIMING_FIELDS: dict[str, TimingFieldDef] = {
    "09": TimingFieldDef(
        "09", "Entry Delay #1", "Entry delay 1, in units of 15 seconds (0, or 2-15).", True
    ),
    "10": TimingFieldDef(
        "10", "Exit Delay #1", "Exit delay 1, in units of 15 seconds (0, or 2-15).", True
    ),
    "11": TimingFieldDef(
        "11",
        "Entry Delay #2",
        "Entry delay 2, in units of 15 seconds (must be >= entry delay 1).",
        True,
    ),
    "12": TimingFieldDef(
        "12",
        "Exit Delay #2",
        "Exit delay 2, in units of 15 seconds (must be >= exit delay 1).",
        True,
    ),
}


class CommercialVistaDialect:
    """VISTA-128BP/250BP dialect: ``<code>8000`` entry, ``*09``-``*12`` timing.

    Supports guided **timing** only. The ``#93`` zone-programming menu is
    conditional and interactive (per-zone-type prompt branches, wireless serial
    enrollment) and is deliberately not driven blind -- so ``GuidedOp.ZONE`` and
    ``FUNCTION_KEY`` are absent and those services refuse commercial panels. The
    zone-type table above is reference/inventory only.
    """

    family = PanelFamily.VISTA
    supported_guided_ops = frozenset({GuidedOp.TIMING})
    guided_field_programming_note = (
        "Commercial VISTA (128BP/250BP): guided *timing* (*09-*12) is supported; "
        "zone programming uses the conditional #93 menu and is not driven here. "
        "The timing builder is guide-derived (K5894PRV6), not hardware-confirmed."
    )

    def zone_types(self) -> dict[int, ZoneTypeDef]:
        return _COMMERCIAL_VISTA_ZONE_TYPES

    def life_safety_zone_codes(self) -> frozenset[int]:
        return _COMMERCIAL_LIFE_SAFETY

    def program_mode_wrapper(self, installer_code: str, action_keystrokes: str) -> str:
        # Commercial panels open Program Mode with <code>8000 (not 800) and exit
        # with *99 (never *98, the lockout exit) -- same as residential.
        return f"{installer_code}8000{action_keystrokes}*99"

    def opens_program_mode(self, keys: str, installer_code: str | None) -> bool:
        return _vista_opens_program_mode(keys, installer_code, "8000")

    def timing_fields(self) -> dict[str, TimingFieldDef]:
        return _COMMERCIAL_TIMING_FIELDS

    def build_timing_keystrokes(self, field_key: str, value: int, partition: int) -> str:
        if field_key not in _COMMERCIAL_TIMING_FIELDS:
            raise ValueError(f"unknown commercial timing field {field_key!r}")
        if not (value == 0 or 2 <= value <= 15):
            raise ValueError(f"{field_key} must be 0 or 2-15 (units of 15 seconds), got {value}")
        if not 1 <= partition <= 8:
            raise ValueError(f"partition must be 1-8, got {partition}")
        # Select the partition (*91<p>), then edit the 2-digit field (*<ff><vv>).
        return f"*91{partition}*{field_key}{value:02d}"


COMMERCIAL_VISTA_DIALECT: PanelDialect = CommercialVistaDialect()


VISTA_MODELS: tuple[PanelModel, ...] = (
    PanelModel(
        model_id="vista_21ip",
        family=PanelFamily.VISTA,
        label="Honeywell VISTA-21iP",
        max_zones=64,
        max_partitions=3,
        verification=Verification.VERIFIED,
        notes="Built from the VISTA-21iP/21iPSIA Programming Guide (K14488PRV3).",
        default_zones=8,
        default_partitions=1,
        aliases=("vista21ip", "vista-21ip", "21ip"),
    ),
    PanelModel(
        model_id="vista_20p",
        family=PanelFamily.VISTA,
        label="Honeywell VISTA-20P",
        max_zones=48,
        max_partitions=3,
        verification=Verification.VERIFIED,
        notes=(
            "Verified field-by-field against the VISTA-15P/20P Programming Guide "
            "(2026-07-05): program-mode grammar, zone types, and *34/*35/*36/*84 "
            "timing fields are identical to the 21iP. 48 zones, partitioned."
        ),
        default_zones=8,
        default_partitions=1,
        aliases=("vista20p", "vista-20p", "20p"),
    ),
    PanelModel(
        model_id="vista_15p",
        family=PanelFamily.VISTA,
        label="Honeywell VISTA-15P",
        max_zones=32,
        max_partitions=1,
        verification=Verification.VERIFIED,
        notes=(
            "Verified against the VISTA-15P/20P Programming Guide (2026-07-05): "
            "same programming language and zone types as the 20P/21iP. "
            "Single-partition, 32 zones (1-6, 9-34, 49-56)."
        ),
        default_zones=6,
        default_partitions=1,
        aliases=("vista15p", "vista-15p", "15p"),
    ),
    PanelModel(
        model_id="vista_10p",
        family=PanelFamily.VISTA,
        label="Honeywell VISTA-10P",
        max_zones=22,
        max_partitions=1,
        verification=Verification.VERIFIED,
        notes=(
            "Verified against the VISTA-10P Programming Guide (2026-07-05): "
            "program-mode grammar, zone types (incl. 14 CO), and *34/*35/*36 "
            "timing fields identical to the 21iP. Zones 1-6 hardwired + 9-24 RF "
            "(no zones 7-8), single partition. *84 auto-stay default is 1 (a "
            "default value only)."
        ),
        default_zones=6,
        default_partitions=1,
        aliases=("vista10p", "vista-10p", "10p"),
    ),
    PanelModel(
        model_id="vista_128bp",
        family=PanelFamily.VISTA,
        label="Honeywell VISTA-128BP",
        max_zones=128,
        max_partitions=8,
        verification=Verification.PROVISIONAL,
        dialect_id="vista_commercial",
        notes=(
            "Commercial panel (K5894PRV6): <code>8000 entry, #93 menu zone "
            "programming, *09-*12 timing in 15-second units. Guided *timing* is "
            "supported (guide-derived, not hardware-confirmed -- stays "
            "PROVISIONAL); guided zone programming (#93) is not driven blind. "
            "Arm/disarm/bypass/model selection work."
        ),
        default_zones=8,
        default_partitions=1,
        aliases=("vista128bp", "vista-128bp", "128bp", "vista128"),
    ),
    PanelModel(
        model_id="vista_250bp",
        family=PanelFamily.VISTA,
        label="Honeywell VISTA-250BP",
        max_zones=250,
        max_partitions=8,
        verification=Verification.PROVISIONAL,
        dialect_id="vista_commercial",
        notes=(
            "Large commercial panel; same K5894PRV6 programming language as the "
            "128BP. Guided *timing* (*09-*12) supported (guide-derived, "
            "PROVISIONAL); #93 zone programming not driven. "
            "Arm/disarm/bypass/model selection work."
        ),
        default_zones=8,
        default_partitions=1,
        aliases=("vista250bp", "vista-250bp", "250bp", "vista250"),
    ),
)
