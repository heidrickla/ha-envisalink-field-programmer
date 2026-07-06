"""Honeywell/Ademco VISTA family dialect.

Program-Mode grammar (``<installer code>800`` to open, ``*99`` to exit, ``*56``
zone menu, ``*57`` function-key menu, ``*34``/``*35``/``*36`` timing fields) is
the long-standing, stable convention across the residential VISTA line and is
reused directly from :mod:`field_programming`, which was built strictly from
the VISTA-21iP/21iPSIA Programming Guide (K14488PRV3).

Per-model honesty (see :class:`~.base.Verification`):

  * **VISTA-21iP** -- VERIFIED. This is the panel the whole field-programming
    layer was written and (partially) hardware-tested against.
  * **VISTA-20P / 15P / 10P** -- GRAMMAR_VERIFIED. These are the residential
    siblings of the 21iP (the 21iP is essentially a 20P with onboard IP). They
    share the same ``*56``/``*57``/``800``/``*99`` programming grammar and the
    same zone-type table; what differs and is *not* individually reconfirmed
    here is exact zone/partition capacity handling and a handful of field
    numbers on the older 10P. Capacities below are the documented maximums.
  * **VISTA-128BP / 250BP** -- PROVISIONAL. The commercial panels enter Program
    Mode the same way but use a materially larger and different data-field set
    (and a different guide entirely). Their zone-type table is reused from the
    residential set as a best effort **and must not be trusted** until checked
    against the 128BP/250BP programming guide. They are included so the model
    can be selected and basic arm/disarm/bypass works; guided field
    programming against them should be treated as unverified.
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
        verification=Verification.GRAMMAR_VERIFIED,
        notes=(
            "Residential sibling of the 21iP; shares its *56/*57/800/*99 "
            "programming grammar and zone types. Field numbers assumed "
            "identical to the 21iP -- spot-check against the 20P guide."
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
        verification=Verification.GRAMMAR_VERIFIED,
        notes=(
            "Single-partition residential panel; same programming grammar and "
            "zone types as the 20P/21iP. Capacity is the documented maximum."
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
        verification=Verification.PROVISIONAL,
        notes=(
            "Older single-partition panel. Program-Mode grammar matches the "
            "family, but some field numbers on this generation differ -- verify "
            "against the VISTA-10P guide before real-hardware field programming."
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
        notes=(
            "Commercial panel. Opens Program Mode the same way, but its data "
            "field set differs substantially from the residential guide. Guided "
            "field programming is UNVERIFIED for this model -- treat zone types "
            "and field numbers as placeholders until checked against the 128BP "
            "programming guide. Arm/disarm/bypass are unaffected."
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
        notes=(
            "Large commercial panel; same caveat as the 128BP. Guided field "
            "programming is UNVERIFIED -- verify against the 250BP guide."
        ),
        default_zones=8,
        default_partitions=1,
        aliases=("vista250bp", "vista-250bp", "250bp", "vista250"),
    ),
)
