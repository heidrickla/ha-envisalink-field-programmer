"""Plain-data state models for Vista Console.

These are intentionally framework-free (no Home Assistant imports) so they
can be constructed and asserted against in unit tests without spinning up
any part of Home Assistant.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .const import (
    ARM_MODE_AWAY,
    ARM_MODE_STAY,
    ARM_MODE_ZERO_ENTRY_AWAY,
    ARM_MODE_ZERO_ENTRY_STAY,
)

ARM_MODE_TO_STATE = {
    ARM_MODE_AWAY: "armed_away",
    ARM_MODE_STAY: "armed_home",
    ARM_MODE_ZERO_ENTRY_AWAY: "armed_away",
    ARM_MODE_ZERO_ENTRY_STAY: "armed_night",
}


@dataclass
class ZoneState:
    """State of a single Vista zone as reported over the keybus.

    ``partition`` defaults to 1 because several zone events (605/606/609/610)
    do not carry partition information on the wire. It is refined to the
    correct value whenever a 601-604 event (which does carry a partition)
    is observed for this zone. For single-partition installs (the common
    residential case) this default is always correct.
    """

    number: int
    name: str | None = None
    partition: int = 1
    open: bool = False
    alarm: bool = False
    tamper: bool = False
    fault: bool = False
    bypassed: bool = False


@dataclass
class PartitionState:
    """State of a single Vista partition."""

    number: int
    ready: bool = False
    force_arm_enabled: bool = False
    armed: bool = False
    arm_state: str = "disarmed"
    alarm: bool = False
    exit_delay: bool = False
    entry_delay: bool = False
    chime_enabled: bool = False
    trouble: bool = False
    busy: bool = False
    failed_to_arm: bool = False
    keypad_lockout: bool = False
    last_user: str | None = None


@dataclass
class SystemState:
    """Whole-system, non-partition-specific state."""

    installers_mode: bool = False
    ac_trouble: bool = False
    battery_trouble: bool = False
    bell_trouble: bool = False
    ftc_trouble: bool = False
    fire_trouble: bool = False
    general_tamper: bool = False
    connected: bool = False


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
