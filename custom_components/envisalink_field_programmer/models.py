"""Plain-data state models for Envisalink Field Programmer.

These are intentionally framework-free (no Home Assistant imports) so they
can be constructed and asserted against in unit tests without spinning up
any part of Home Assistant.

Field selection here reflects what the real Envisalink TPI protocol
actually exposes for a Honeywell/Ademco panel (see client.py's module
docstring): per-partition icon-LED flags from ``%00`` keypad updates, plus
the ``%FF`` zone timer dump for zone open/closed state. Notably, this
protocol has no per-zone alarm/tamper/fault reporting and no per-zone
bypass reporting without parsing the keypad's free-text "alpha" display,
which this integration deliberately does not attempt to parse (it's a
fragile, panel-firmware-dependent heuristic in the reference
implementation). Zone bypass is therefore tracked as a best-effort local flag: set
optimistically when this integration itself sends the bypass toggle
keystrokes for a zone, and cleared for every zone in a partition once that
partition's ``bypass`` icon flag reports no bypass active (e.g. after a
disarm/rearm cycle). It will not reflect a bypass toggled from the
physical keypad rather than through this integration.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ZoneState:
    """State of a single Vista zone.

    ``open`` is derived from the periodic zone timer dump (``%FF``): a zone
    is considered open if its timer is within a few ticks of full (see
    state_machine.py), matching how the reference `pyenvisalink`
    implementation interprets this same data.

    ``partition`` defaults to 1 and is never refined from wire data -- the
    real protocol's zone timer dump has no per-zone partition tagging, and
    per-zone reporting in ``%00`` keypad updates would need the same
    alpha-text heuristic parsing this integration avoids (see the module
    docstring). Correct for single-partition installs, the common
    residential case.
    """

    number: int
    name: str | None = None
    partition: int = 1
    open: bool = False
    bypassed: bool = False
    seconds_since_fault: float | None = None


@dataclass
class PartitionState:
    """State of a single Vista partition, as reported by its keypad's icon LEDs."""

    number: int
    ready: bool = False
    armed: bool = False
    arm_state: str = "disarmed"
    alarm: bool = False
    alarm_in_memory: bool = False
    alarm_fire_zone: bool = False
    fire: bool = False
    exit_delay: bool = False
    chime_enabled: bool = False
    ac_present: bool = True
    low_battery: bool = False
    trouble: bool = False
    bypass_active: bool = False
    last_armed_by_user: str | None = None
    last_disarmed_by_user: str | None = None

    @property
    def last_user(self) -> str | None:
        """Most recent of last_armed_by_user/last_disarmed_by_user, for display."""
        return self.last_disarmed_by_user or self.last_armed_by_user


@dataclass
class SystemState:
    """Whole-system, non-partition-specific state."""

    connected: bool = False
    installers_mode: bool = False


@dataclass
class VistaState:
    """Aggregate state for the whole panel, as seen through the EVL."""

    partitions: dict[int, PartitionState] = field(default_factory=dict)
    zones: dict[int, ZoneState] = field(default_factory=dict)
    system: SystemState = field(default_factory=SystemState)

    @classmethod
    def create(cls, num_partitions: int, num_zones: int) -> VistaState:
        return cls(
            partitions={n: PartitionState(number=n) for n in range(1, num_partitions + 1)},
            zones={n: ZoneState(number=n) for n in range(1, num_zones + 1)},
        )

    def partition(self, number: int) -> PartitionState:
        return self.partitions.setdefault(number, PartitionState(number=number))

    def zone(self, number: int) -> ZoneState:
        return self.zones.setdefault(number, ZoneState(number=number))
