"""DSC PowerSeries family dialect.

DSC panels use a completely different programming language from Honeywell
VISTA -- **section-based**, not ``*56`` field menus:

  * Installer programming opens with ``*8`` followed by the installer code
    (factory default ``5555``).
  * You then key a 3-digit **section** number and enter that section's data
    positionally.
  * ``#`` backs out of a section; keying out to the top and pressing ``#``
    again exits programming (represented here as ``##``).

Zone definitions live in sections 001..008 (each section holds eight zones,
entered as fixed-width codes back-to-back), and partition timers live in
section 005. Because a zone-definition section is **positional** -- you re-key
all eight zones in order, with no read-back over TPI to preserve the ones you
aren't changing -- this integration deliberately does **not** expose its
VISTA-shaped per-zone guided programming for DSC. Doing so blind would risk
silently overwriting the other seven zones in a block, which on a fire zone is
exactly the class of mistake this project's guard exists to prevent.

What this dialect *does* provide, and stands behind at the grammar level:

  * correct Program-Mode entry/exit wrapping (so the safety guard can refuse
    ``*8<code>`` by default, the DSC analogue of VISTA's ``<code>800``);
  * a documented DSC zone-type reference table.

Everything model-specific here is :class:`~.base.Verification.PROVISIONAL`:
the grammar is stable and well known, but the per-model zone/partition
capacities and the exact zone-type code numbers vary across PowerSeries
generations (the older PC1555/5010/5020 use different widths/codes than the
PC1616/1832/1864) and are **not** verified against each panel's own installation
manual. Verify before trusting on real hardware.

Note also that the current :mod:`client` transport speaks Honeywell TPI framing;
wiring DSC arm/disarm/zone state is a separate future effort. This dialect is
the programming-language half of that work, added now so the abstraction is in
place and model selection is possible.
"""
from __future__ import annotations

import re

from .base import PanelFamily, PanelModel, Verification, ZoneTypeDef

DSC_PROGRAM_MODE_PREFIX = "*8"
DSC_EXIT_PROGRAM_MODE = "##"

# Representative DSC PowerSeries zone-type ("zone definition") reference.
# PROVISIONAL: reflects the standard PowerSeries categories, but exact numeric
# codes differ between generations -- confirm against your panel's manual.
_DSC_ZONE_TYPES: dict[int, ZoneTypeDef] = {
    0: ZoneTypeDef(0, "Null (unused)", "Zone disabled / not monitored."),
    1: ZoneTypeDef(
        1, "Delay 1", "Primary entry/exit door with entry/exit delay 1."
    ),
    2: ZoneTypeDef(
        2, "Delay 2", "Secondary entry/exit door with the longer entry/exit delay 2."
    ),
    3: ZoneTypeDef(3, "Instant", "Perimeter door/window; alarms immediately when armed."),
    4: ZoneTypeDef(
        4, "Interior", "Interior follower; delayed only if an entry door tripped first."
    ),
    5: ZoneTypeDef(
        5, "Interior Stay/Away", "Interior zone automatically bypassed when armed Stay."
    ),
    6: ZoneTypeDef(
        6, "Delay Stay/Away", "Entry/exit zone that is auto-bypassed when armed Stay."
    ),
    7: ZoneTypeDef(
        7,
        "24-Hour Fire (delayed)",
        "Smoke/heat detector, always active with a verification delay. Life safety.",
        life_safety=True,
    ),
    8: ZoneTypeDef(
        8, "24-Hour Bell", "Always-armed burglary zone that sounds the bell."
    ),
    9: ZoneTypeDef(
        9,
        "24-Hour Fire",
        "Smoke/heat detector, always active, cannot be bypassed. Life safety.",
        life_safety=True,
    ),
    13: ZoneTypeDef(
        13,
        "24-Hour Carbon Monoxide",
        "CO detector, always active. Life safety.",
        life_safety=True,
    ),
    24: ZoneTypeDef(
        24,
        "24-Hour Panic (silent)",
        "Hold-up/panic; silent report to the monitoring station only.",
    ),
    25: ZoneTypeDef(
        25, "24-Hour Panic (audible)", "Hold-up/panic; sounds the bell and reports."
    ),
}

_DSC_LIFE_SAFETY_CODES = frozenset(
    code for code, zt in _DSC_ZONE_TYPES.items() if zt.life_safety
)


class DscPowerSeriesDialect:
    """Shared dialect for every DSC PowerSeries model."""

    family = PanelFamily.DSC_POWERSERIES
    supports_guided_field_programming = False
    guided_field_programming_note = (
        "DSC PowerSeries uses positional, whole-section zone programming rather "
        "than VISTA's per-zone *56 menu, and the current transport speaks "
        "Honeywell TPI. Model selection, the zone-type reference, and the "
        "installer-mode safety guard are available; guided per-zone programming "
        "is not driven for DSC (it would risk overwriting an entire 8-zone "
        "block blind). Verify any DSC programming against the panel's manual."
    )

    def zone_types(self) -> dict[int, ZoneTypeDef]:
        return _DSC_ZONE_TYPES

    def life_safety_zone_codes(self) -> frozenset[int]:
        return _DSC_LIFE_SAFETY_CODES

    def program_mode_wrapper(self, installer_code: str, action_keystrokes: str) -> str:
        """Wrap section keystrokes: ``*8`` + code + <sections> + ``##``."""
        return (
            f"{DSC_PROGRAM_MODE_PREFIX}{installer_code}"
            f"{action_keystrokes}{DSC_EXIT_PROGRAM_MODE}"
        )

    def opens_program_mode(self, keys: str, installer_code: str | None) -> bool:
        """DSC opens installer programming via ``*8`` + installer code.

        Matches the exact configured code after ``*8`` or, code-agnostically,
        ``*8`` immediately followed by a 4-6 digit run.
        """
        if installer_code and f"{DSC_PROGRAM_MODE_PREFIX}{installer_code}" in keys:
            return True
        return bool(re.search(r"\*8\d{4,6}", keys))


DSC_DIALECT = DscPowerSeriesDialect()


def _dsc(model_id, label, max_zones, max_partitions, notes, aliases=()):
    return PanelModel(
        model_id=model_id,
        family=PanelFamily.DSC_POWERSERIES,
        label=label,
        max_zones=max_zones,
        max_partitions=max_partitions,
        verification=Verification.PROVISIONAL,
        notes="PROVISIONAL: " + notes,
        default_zones=min(8, max_zones),
        default_partitions=1,
        aliases=aliases,
    )


# Capacities are the commonly-documented PowerSeries maximums, but are marked
# PROVISIONAL along with everything else DSC here -- confirm per panel.
DSC_MODELS: tuple[PanelModel, ...] = (
    _dsc("dsc_pc1555", "DSC PC1555", 8, 2,
         "Entry-level PowerSeries. Confirm zone/partition capacity and codes.",
         aliases=("pc1555", "1555")),
    _dsc("dsc_pc1555mx", "DSC PC1555MX", 32, 2,
         "Confirm max zones (base is smaller, expandable) against the manual.",
         aliases=("pc1555mx", "1555mx")),
    _dsc("dsc_pc1575", "DSC PC1575", 32, 2,
         "Model identifier and capacity unconfirmed -- verify against the panel.",
         aliases=("pc1575", "1575")),
    _dsc("dsc_pc5010", "DSC PC5010 (Power832)", 32, 2,
         "Marketing name Power832. Confirm capacity and section codes.",
         aliases=("pc5010", "5010", "power832", "832")),
    _dsc("dsc_pc5020", "DSC PC5020 (Power864)", 64, 8,
         "Marketing name Power864. Confirm capacity and section codes.",
         aliases=("pc5020", "5020", "power864", "864")),
    _dsc("dsc_pc1616", "DSC PC1616", 16, 2,
         "16-zone PowerSeries. Zone-definition codes are 3-digit on this "
         "generation -- verify the table before use.",
         aliases=("pc1616", "1616")),
    _dsc("dsc_pc1832", "DSC PC1832", 32, 4,
         "32-zone PowerSeries. Same 3-digit zone-definition caveat as the 1616.",
         aliases=("pc1832", "1832")),
    _dsc("dsc_pc1864", "DSC PC1864", 64, 8,
         "64-zone PowerSeries. Same 3-digit zone-definition caveat as the 1616.",
         aliases=("pc1864", "1864")),
)
