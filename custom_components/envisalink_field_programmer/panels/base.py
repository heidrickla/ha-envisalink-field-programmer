"""Panel-dialect abstraction shared by every supported alarm panel family.

This integration was originally built against a single panel, the Honeywell
VISTA-21iP, with its field-programming grammar (``*56`` zone menus,
``<installer code>800`` to open Program Mode, ``*99`` to exit) baked directly
into :mod:`field_programming` and :mod:`programming`. Supporting other panels
means those hard-coded assumptions have to become *data*, selected per config
entry.

A **dialect** captures everything that differs between panel families:

  * how Program Mode is opened and closed (VISTA ``<code>800`` / ``*99`` vs.
    DSC PowerSeries ``*8<code>`` / ``##``);
  * what a zone-type code means and which codes are life-safety;
  * how a validated zone/timing edit is turned into keystrokes;
  * what a "this opens installer programming" sequence looks like on the wire
    (so the safety guard in :mod:`programming` can refuse it by default).

A **model** is one concrete panel within a family, carrying its capacity
(zones/partitions) and -- critically -- a :class:`Verification` level saying
how much of its per-model data has actually been checked against that panel's
own programming guide versus inferred from a related panel.

Nothing in this module (or any dialect) talks to the panel. Dialects only
describe *what a field means* and *what keystrokes express it*; sending still
goes through :func:`programming.async_send_guarded_keystrokes`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class PanelFamily(StrEnum):
    """Top-level programming-language family."""

    VISTA = "vista"
    """Honeywell/Ademco VISTA -- ``*56``-style field/menu programming."""

    DSC_POWERSERIES = "dsc_powerseries"
    """DSC PowerSeries -- ``*8``-style section-based programming."""


class Verification(StrEnum):
    """How much of a model's per-model programming data has been confirmed.

    This is a first-class, user-visible attribute on purpose. This project's
    entire safety posture is built on *not* sending unverified keystrokes to
    real fire/security hardware, so a model must be honest about how much of
    its data is actually trustworthy. The guided-programming services surface
    this level and refuse to run against anything below VERIFIED unless the
    caller explicitly acknowledges the risk.
    """

    VERIFIED = "verified"
    """Built directly from this exact panel's own programming guide, and/or
    confirmed against the real hardware. Currently only the VISTA-21iP."""

    GRAMMAR_VERIFIED = "grammar_verified"
    """The Program-Mode entry/exit and zone-programming *mechanism* is the
    documented, stable convention for this family and is trusted, but this
    specific model's field numbers / zone-type codes have not been checked
    one-by-one against its own guide -- they are inherited from a closely
    related panel in the same family. Treat individual field numbers as
    likely-correct-but-unconfirmed."""

    PROVISIONAL = "provisional"
    """Per-model field numbers and/or zone-type codes are reconstructed from
    general family knowledge, not this model's guide. Must be verified against
    the actual programming guide (and ideally the real panel, in review-only
    mode) before being trusted on a live fire/security zone."""


VERIFICATION_LABELS: dict[Verification, str] = {
    Verification.VERIFIED: "Verified against this panel's programming guide",
    Verification.GRAMMAR_VERIFIED: (
        "Programming grammar verified; per-model field numbers inherited from a "
        "related panel and not individually confirmed"
    ),
    Verification.PROVISIONAL: (
        "Provisional -- verify every field against this panel's own programming "
        "guide before using on real hardware"
    ),
}


@dataclass(frozen=True)
class ZoneTypeDef:
    """One zone-type option, family-agnostic.

    ``code`` is the family-native value entered at the keypad (an int for
    VISTA's 1-2 digit types; DSC's 3-digit codes are also representable as
    ints, formatted to width by the dialect). ``life_safety`` drives the
    extra-loud confirmation gate for fire/CO/panic types.
    """

    code: int
    label: str
    description: str
    life_safety: bool = False


@dataclass(frozen=True)
class PanelModel:
    """Static metadata describing one concrete panel model."""

    model_id: str
    """Stable identifier stored in the config entry, e.g. ``"vista_21ip"``."""
    family: PanelFamily
    label: str
    """Human-facing name, e.g. ``"Honeywell VISTA-21iP"``."""
    max_zones: int
    max_partitions: int
    verification: Verification
    notes: str = ""
    """Short free-text caveat surfaced in the UI/logs (e.g. what to check)."""

    default_zones: int = 8
    default_partitions: int = 1

    aliases: tuple[str, ...] = field(default_factory=tuple)
    """Alternate model spellings that should resolve to this entry."""

    supports_guided_field_programming: bool | None = None
    """Per-model override of the family dialect's guided-programming support.

    ``None`` means "defer to the dialect." Set ``False`` for a model that lives
    in a guided-capable family but whose own programming language differs enough
    that the family's guided builder would emit wrong keystrokes -- e.g. the
    commercial VISTA-128BP/250BP, which use ``#93`` menu zone programming and
    ``*09``-``*12`` timing fields rather than the residential ``*56``/``*34``
    flow this integration's guided services drive."""


@runtime_checkable
class PanelDialect(Protocol):
    """Everything family-specific about turning intent into keystrokes.

    One dialect instance serves every model in its family; per-model
    differences (capacity, verification) live on :class:`PanelModel`, which is
    passed in where it matters (e.g. capacity validation).
    """

    family: PanelFamily

    supports_guided_field_programming: bool
    """Whether this integration's guided *per-zone* programming flow
    (``program_zone`` / ``set_system_timing`` / ``program_function_key``)
    applies to this family. VISTA's ``*56`` menu is per-zone and maps cleanly;
    DSC's section-based programming rewrites a whole 8-zone block positionally,
    which is a different shape this integration does not yet drive -- so DSC
    exposes model metadata, zone-type reference, and the safety guard, but not
    the guided per-zone services."""

    guided_field_programming_note: str
    """Human-facing explanation shown when guided programming is unavailable
    or unverified for the selected model."""

    def zone_types(self) -> dict[int, ZoneTypeDef]:
        """Return the code -> :class:`ZoneTypeDef` table for this family."""

    def life_safety_zone_codes(self) -> frozenset[int]:
        """Zone-type codes that detect fire/CO (extra confirmation gate)."""

    def program_mode_wrapper(self, installer_code: str, action_keystrokes: str) -> str:
        """Wrap in-Program-Mode keystrokes with this family's entry + exit."""

    def opens_program_mode(self, keys: str, installer_code: str | None) -> bool:
        """True if ``keys`` would open installer Program Mode on this family.

        Used by the safety guard to refuse such sequences unless explicitly
        acknowledged. Must be conservative: prefer a false positive (an
        over-cautious refusal) to letting an installer-mode sequence through.
        """
