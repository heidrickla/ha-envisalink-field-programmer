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
  * **VISTA-128BP / 250BP** -- PROVISIONAL, and guided programming is **disabled**
    for them (``supports_guided_field_programming=False``). Checked against the
    K5894PRV6 guide (2026-07-05): these commercial panels genuinely use a
    *different* programming language -- program mode opens with ``<code>8000``
    (not ``<code>800``), zones are programmed through ``#93`` menu mode (not
    ``*56``), and entry/exit timing lives in fields ``*09``-``*12`` in 15-second
    units (not ``*34``/``*35``/``*36`` in raw seconds). Driving the residential
    ``*56``/``*34`` builder against them would send wrong keystrokes, so the
    guided services refuse them (arm/disarm/bypass and model selection still
    work). A proper commercial-VISTA dialect (#93 + ``*09``-``*12``) is a
    separate future effort.
"""
from __future__ import annotations

from ..field_programming import (
    LIFE_SAFETY_ZONE_TYPE_CODES,
    ZONE_TYPES,
    build_program_mode_wrapper,
)
from .base import PanelDialect, PanelFamily, PanelModel, Verification, ZoneTypeDef

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


class VistaDialect:
    """Shared dialect for every VISTA-family model."""

    family = PanelFamily.VISTA
    supports_guided_field_programming = True
    guided_field_programming_note = (
        "VISTA *56 zone programming is per-zone and fully wired into the guided "
        "flow."
    )

    def zone_types(self) -> dict[int, ZoneTypeDef]:
        return _VISTA_ZONE_TYPES

    def life_safety_zone_codes(self) -> frozenset[int]:
        return LIFE_SAFETY_ZONE_TYPE_CODES

    def program_mode_wrapper(self, installer_code: str, action_keystrokes: str) -> str:
        return build_program_mode_wrapper(installer_code, action_keystrokes)

    def opens_program_mode(self, keys: str, installer_code: str | None) -> bool:
        """VISTA opens Program Mode via ``<installer code>800``.

        Matches either the exact configured code followed by ``800`` or, as a
        code-agnostic fallback, any run of 4-6 digits immediately followed by
        ``800`` -- which is what an installer-code entry looks like on the wire
        regardless of the code in use.
        """
        import re

        if installer_code and f"{installer_code}800" in keys:
            return True
        return bool(re.search(r"\d{4,6}800", keys))


VISTA_DIALECT: PanelDialect = VistaDialect()


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
        supports_guided_field_programming=False,
        notes=(
            "Commercial panel. Confirmed against K5894PRV6 (2026-07-05) to use a "
            "different programming language than the residential line: <code>8000 "
            "entry, #93 menu zone programming, *09-*12 timing in 15-second units. "
            "Guided programming is disabled (the residential *56/*34 builder would "
            "send wrong keystrokes); arm/disarm/bypass/model selection work. Needs "
            "a dedicated commercial-VISTA dialect."
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
        supports_guided_field_programming=False,
        notes=(
            "Large commercial panel; shares the 128BP's K5894PRV6 programming "
            "language (#93 zone programming, *09-*12 timing, <code>8000 entry), "
            "not the residential *56/*34 flow. Guided programming disabled; "
            "arm/disarm/bypass/model selection work. Needs the same dedicated "
            "commercial-VISTA dialect as the 128BP."
        ),
        default_zones=8,
        default_partitions=1,
        aliases=("vista250bp", "vista-250bp", "250bp", "vista250"),
    ),
)
