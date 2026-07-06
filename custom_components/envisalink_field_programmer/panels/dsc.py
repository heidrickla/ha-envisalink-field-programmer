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

The section grammar and the zone-definition code table below were checked
against real DSC installation manuals (2026-07-05): the PC1616/PC1832/PC1864
v4.6 guide (source of the code table), the PC1555MX manual, and the PC5020/
Power864 manual all use the same ``[*][8][code]`` entry, ``[001]``-``[004]``
zone-definition sections and ``[005]`` partition timing. Per-model capacities
are guide-confirmed where noted on each :class:`~.base.PanelModel`; a couple
(PC5010/Power832, whose obtained PDF is a scanned image, and PC1555) still rest
on general knowledge.

All DSC models remain :class:`~.base.Verification.PROVISIONAL` regardless,
because this integration does **not** offer guided programming for DSC (see
``supports_guided_field_programming`` below) -- there is no guided keystroke
path to "verify," and the current :mod:`client` transport speaks Honeywell TPI
framing, so wiring DSC arm/disarm/zone state is a separate future effort. This
dialect is the programming-language reference + safety guard half of that work;
the code table is inventory/reference, not a keystroke source.
"""
from __future__ import annotations

import re

from .base import PanelFamily, PanelModel, Verification, ZoneTypeDef

DSC_PROGRAM_MODE_PREFIX = "*8"
DSC_EXIT_PROGRAM_MODE = "##"

# DSC PowerSeries zone-definition ("zone type") reference, taken from the
# PC1616/PC1832/PC1864 v4.6 Installation Guide sections [001]-[004] (verified
# 2026-07-05; the PC1555MX and PC5020/Power864 guides use the same grammar and
# core codes). Reference/inventory only -- this integration does not drive DSC
# zone programming (see the module docstring), so nothing here builds keystrokes.
_DSC_ZONE_TYPES: dict[int, ZoneTypeDef] = {
    0: ZoneTypeDef(0, "Null (unused)", "Zone disabled / not monitored."),
    1: ZoneTypeDef(1, "Delay 1", "Entry/exit door; follows Entry Delay 1 when armed."),
    2: ZoneTypeDef(2, "Delay 2", "Entry/exit door; follows the longer Entry Delay 2."),
    3: ZoneTypeDef(3, "Instant", "Perimeter door/window; instant alarm when armed."),
    4: ZoneTypeDef(
        4, "Interior", "Interior follower; delayed only if an entry door tripped first."
    ),
    5: ZoneTypeDef(
        5, "Interior Stay/Away", "Interior zone auto-bypassed when armed in Stay mode."
    ),
    6: ZoneTypeDef(
        6, "Delay Stay/Away", "Delay-1 zone auto-bypassed when armed in Stay mode."
    ),
    7: ZoneTypeDef(
        7,
        "Delayed 24-Hour Fire",
        "Hardwired smoke/heat detector; instant audible alarm, communication "
        "delayed 30s. Always active. Life safety.",
        life_safety=True,
    ),
    8: ZoneTypeDef(
        8,
        "Standard 24-Hour Fire",
        "Hardwired smoke/heat detector; instant alarm and communication. Always "
        "active. Life safety.",
        life_safety=True,
    ),
    9: ZoneTypeDef(
        9,
        "24-Hour Supervision",
        "Instant alarm/communication; does not sound the bell or keypad buzzer.",
    ),
    10: ZoneTypeDef(
        10, "24-Hour Supervisory Buzzer", "Instant alarm; sounds the keypad buzzer."
    ),
    11: ZoneTypeDef(11, "24-Hour Burglary", "Always-armed burglary zone; audible alarm."),
    16: ZoneTypeDef(
        16, "24-Hour Panic", "Hold-up/panic zone; reports to the monitoring station."
    ),
    41: ZoneTypeDef(
        41,
        "24-Hour Carbon Monoxide (hardwired)",
        "Hardwired CO detector with distinct bell cadence. Life safety.",
        life_safety=True,
    ),
    81: ZoneTypeDef(
        81,
        "24-Hour Carbon Monoxide (wireless)",
        "Wireless CO detector with distinct bell cadence. Life safety.",
        life_safety=True,
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


# Capacities: those marked "(guide-confirmed 2026-07-05)" were read from that
# panel's own installation manual; the rest are commonly-documented maximums
# still awaiting a per-panel check. The whole DSC family stays PROVISIONAL
# because guided programming is disabled for it regardless (see the dialect).
DSC_MODELS: tuple[PanelModel, ...] = (
    _dsc("dsc_pc1555", "DSC PC1555", 32, 2,
         "PowerSeries 6-32 zone panel (max corrected from 8 to 32, 2026-07-05, "
         "per the official 'PC1555 ... PowerSeries 6-32 Zone Control Panel' "
         "manual title); same *8 section grammar as the PC1555MX.",
         aliases=("pc1555", "1555")),
    _dsc("dsc_pc1555mx", "DSC PC1555MX", 32, 2,
         "Grammar + expandable-to-32-zone capacity guide-confirmed 2026-07-05 "
         "(PC1555MX Installation Manual): [*][8][code] entry, sections "
         "[001]-[004] zone definitions, [005] timing.",
         aliases=("pc1555mx", "1555mx")),
    _dsc("dsc_pc1575", "DSC PC1575", 6, 1,
         "PowerSeries 6-zone single-partition panel, guide-confirmed 2026-07-05 "
         "(official JCI PC1575 v1.0 Installation Manual): 6 zones, *8 section "
         "grammar, section 5.2 zone definitions. Corrected from 32 zones / 2 "
         "partitions.",
         aliases=("pc1575", "1575")),
    _dsc("dsc_pc5010", "DSC PC5010 (Power832)", 32, 2,
         "Power832. 32 zones / 2 partitions confirmed 2026-07-05 (Power832 "
         "instruction manual); same *8 section grammar. The installer-manual "
         "PDFs found are scanned images, so the zone-definition table is taken "
         "from the newer PowerSeries guides.",
         aliases=("pc5010", "5010", "power832", "832")),
    _dsc("dsc_pc5020", "DSC PC5020 (Power864)", 64, 8,
         "Power864. 64 zones / 8 partitions guide-confirmed 2026-07-05 (PC5020 "
         "manual); same *8 section grammar and [001]-[004] zone definitions.",
         aliases=("pc5020", "5020", "power864", "864")),
    _dsc("dsc_pc1616", "DSC PC1616", 16, 2,
         "16 zones / 2 partitions guide-confirmed 2026-07-05 (PC1616/1832/1864 "
         "v4.6). Zone-definition reference table taken from this guide.",
         aliases=("pc1616", "1616")),
    _dsc("dsc_pc1832", "DSC PC1832", 32, 4,
         "32 zones / 4 partitions guide-confirmed 2026-07-05 (PC1616/1832/1864 "
         "v4.6).",
         aliases=("pc1832", "1832")),
    _dsc("dsc_pc1864", "DSC PC1864", 64, 8,
         "64 zones / 8 partitions guide-confirmed 2026-07-05 (PC1616/1832/1864 "
         "v4.6).",
         aliases=("pc1864", "1864")),
)
