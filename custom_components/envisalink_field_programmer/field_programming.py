"""Structured, plain-language Vista field-programming data model.

Source: ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3 10/12
Rev B ("*56 ZONE PROGRAMMING MENU MODE", "ZONE TYPE DEFINITIONS", "*57
FUNCTION KEY PROGRAMMING", and the numbered data-field sections for exit/
entry delay, chime, and auto-stay-arm). Field numbers, prompt order, and
valid ranges are taken directly from that document; the label/description
text below is paraphrased in plain language rather than quoted, and
deliberately narrower than the full manual -- this covers the zone types,
timing, and function keys an ordinary homeowner is likely to actually touch,
not the entire installer field set (output/relay programming, alpha
descriptors, and configurable zone types 90/91 are intentionally out of
scope for now; see the README).

Nothing in this module talks to the panel. It only describes *what a field
means* and, given validated values, *what keystrokes express that meaning*.
Actually sending anything still goes through programming.py's guard.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum

from .const import ENTER_ZONE_PROGRAMMING, EXIT_PROGRAM_MODE, PROGRAM_MODE_SUFFIX


class FieldCategory(StrEnum):
    """Grouping used to lay out the guided UI -- not a Vista concept."""

    LIFE_SAFETY = "life_safety"
    ENTRY_EXIT = "entry_exit"
    PERIMETER_INTERIOR = "perimeter_interior"
    PANIC_EMERGENCY = "panic_emergency"
    SPECIAL = "special"


@dataclass(frozen=True)
class ZoneType:
    """One entry from the Vista "ZONE TYPE DEFINITIONS" table."""

    code: int
    label: str
    description: str
    category: FieldCategory
    life_safety: bool = False
    """True for zone types that detect fire/CO. Changing a zone away from
    one of these (or assigning one incorrectly) can disable real
    life-safety detection -- the guided UI must warn extra loudly here."""


# Deliberately curated, not exhaustive: omits button-transmitter-only types
# (20/21/22, wireless-key specific), AAV monitor (81), keyswitch (77), and
# the installer-only configurable types (90/91) that the guide itself says
# "may not be used as fire or burglar alarm zones" and are meant to be set
# up via downloader software, not a homeowner-facing UI.
ZONE_TYPES: dict[int, ZoneType] = {
    0: ZoneType(
        0,
        "Not used",
        "This zone number has nothing assigned to it.",
        FieldCategory.SPECIAL,
    ),
    1: ZoneType(
        1,
        "Entry/Exit (primary)",
        "Your main door. Gives you time to walk out after arming, and time "
        "to walk in and disarm before an alarm sounds (see Entry Delay 1). "
        "Instant alarm if armed in Instant/Maximum mode.",
        FieldCategory.ENTRY_EXIT,
    ),
    2: ZoneType(
        2,
        "Entry/Exit (secondary)",
        "A second, less-used entry door that needs more time to get to the "
        "keypad than your main door (see Entry Delay 2).",
        FieldCategory.ENTRY_EXIT,
    ),
    3: ZoneType(
        3,
        "Perimeter (instant)",
        "An exterior door or window that should alarm immediately the "
        "moment it opens while armed -- no walk-in delay. Typical for "
        "windows and doors you don't walk through.",
        FieldCategory.PERIMETER_INTERIOR,
    ),
    4: ZoneType(
        4,
        "Interior (follower)",
        "An indoor area you pass through after entering (foyer, hallway). "
        "Gives the normal entry delay only if a delay door was opened "
        "first; otherwise alarms instantly. Automatically ignored when "
        "armed Stay/Instant.",
        FieldCategory.PERIMETER_INTERIOR,
    ),
    9: ZoneType(
        9,
        "Fire (smoke/heat detector)",
        "A hardwired smoke or heat detector. Always active, day or night, "
        "armed or not, and cannot be bypassed. Changing a real smoke "
        "detector's zone away from this type will silence it.",
        FieldCategory.LIFE_SAFETY,
        life_safety=True,
    ),
    16: ZoneType(
        16,
        "Fire with verification",
        "Like Fire, but the panel double-checks (resets the detector and "
        "watches for a second alarm within 90 seconds) before sounding, to "
        "cut down on false alarms. Always active and cannot be bypassed.",
        FieldCategory.LIFE_SAFETY,
        life_safety=True,
    ),
    14: ZoneType(
        14,
        "Carbon monoxide detector",
        "A CO detector. Always active and cannot be bypassed.",
        FieldCategory.LIFE_SAFETY,
        life_safety=True,
    ),
    6: ZoneType(
        6,
        "Panic button (silent)",
        "An emergency button. Notifies the monitoring station only -- no "
        "sound at the keypad or siren.",
        FieldCategory.PANIC_EMERGENCY,
    ),
    7: ZoneType(
        7,
        "Panic button (audible)",
        "An emergency button. Notifies the monitoring station and sounds the keypad and siren.",
        FieldCategory.PANIC_EMERGENCY,
    ),
    8: ZoneType(
        8,
        "Auxiliary alarm (24-hour)",
        "For an emergency button or a monitoring sensor (e.g. water, "
        "temperature). Notifies the monitoring station and beeps the "
        "keypad, but does not sound the siren.",
        FieldCategory.PANIC_EMERGENCY,
    ),
    10: ZoneType(
        10,
        "Interior with delay",
        "Like Interior (follower), but always gives the entry delay when "
        "armed Away, even if no delay door was tripped first. Automatically "
        "ignored when armed Stay/Instant.",
        FieldCategory.PERIMETER_INTERIOR,
    ),
    12: ZoneType(
        12,
        "Monitor (trouble only, no alarm)",
        "Reports faults as a non-alarm 'trouble' condition, not a burglary "
        "alarm. Can be faulted at the time of arming without blocking it. "
        "Do not pair with a relay set to trigger on alarm.",
        FieldCategory.SPECIAL,
    ),
    23: ZoneType(
        23,
        "No alarm response",
        "Never triggers an alarm by itself -- useful when you just want an "
        "output relay action tied to this zone (e.g. a door-access chime), "
        "with no security response.",
        FieldCategory.SPECIAL,
    ),
    24: ZoneType(
        24,
        "Silent burglary",
        "Like Perimeter, but with no audible indication anywhere -- only a "
        "silent report to the monitoring station.",
        FieldCategory.PERIMETER_INTERIOR,
    ),
}

LIFE_SAFETY_ZONE_TYPE_CODES = frozenset(code for code, zt in ZONE_TYPES.items() if zt.life_safety)


class HardwireType(StrEnum):
    """Wiring style for hardwired zones 2-8 (zone 1 is always EOL)."""

    END_OF_LINE = "0"
    NORMALLY_CLOSED = "1"
    NORMALLY_OPEN = "2"
    ZONE_DOUBLING = "3"
    DOUBLE_BALANCED = "4"


HARDWIRE_TYPE_LABELS: dict[HardwireType, str] = {
    HardwireType.END_OF_LINE: "End-of-line resistor (standard, most common)",
    HardwireType.NORMALLY_CLOSED: "Normally closed, no resistor",
    HardwireType.NORMALLY_OPEN: "Normally open, no resistor",
    HardwireType.ZONE_DOUBLING: "Zone doubling (two zones share one input)",
    HardwireType.DOUBLE_BALANCED: "Double-balanced (tamper-resistant)",
}


class ResponseTime(StrEnum):
    """How long a fault must persist before the zone reports it."""

    MS_10 = "0"
    MS_350 = "1"
    MS_700 = "2"
    SEC_1_2 = "3"


RESPONSE_TIME_LABELS: dict[ResponseTime, str] = {
    ResponseTime.MS_10: "10 ms (fastest, standard wired contacts)",
    ResponseTime.MS_350: "350 ms",
    ResponseTime.MS_700: "700 ms",
    ResponseTime.SEC_1_2: "1.2 seconds (slowest, reduces false trips on noisy loops)",
}


@dataclass(frozen=True)
class ZoneProgram:
    """A validated, complete set of *56-equivalent settings for one zone."""

    zone_number: int  # 1-64
    zone_type: int  # key into ZONE_TYPES
    partition: int  # 1-3
    report_enabled: bool = True
    hardwire_type: HardwireType = HardwireType.END_OF_LINE
    response_time: ResponseTime = ResponseTime.MS_350

    def __post_init__(self) -> None:
        if not 1 <= self.zone_number <= 64:
            raise ValueError(f"zone_number must be 1-64, got {self.zone_number}")
        if self.zone_type not in ZONE_TYPES:
            raise ValueError(f"unknown zone_type {self.zone_type}")
        if not 1 <= self.partition <= 3:
            raise ValueError(f"partition must be 1-3, got {self.partition}")

    @property
    def is_hardwired_prompt_zone(self) -> bool:
        """Zones 1-8 get HARDWIRE TYPE / RESPONSE TIME prompts; 9+ don't."""
        return self.zone_number <= 8


def build_zone_program_keystrokes(program: ZoneProgram) -> str:
    """Translate a ZoneProgram into the *56 menu-mode keystroke sequence.

    Does NOT include entering/exiting Program Mode -- see
    build_program_mode_wrapper(). Every entry in *56 mode must be followed
    by "*" to accept it, per the guide's own instructions for this menu.
    """
    keys = [ENTER_ZONE_PROGRAMMING]
    keys.append("0*")  # SET TO CONFIRM? -- no (not enrolling a wireless device)
    keys.append(f"{program.zone_number:02d}*")  # ENTER ZN NUM
    keys.append("*")  # accept SUMMARY SCREEN
    keys.append(f"{program.zone_type:02d}*")  # ZONE TYPE
    keys.append(f"{program.partition}*")  # PARTITION
    keys.append(("1" if program.report_enabled else "00") + "*")  # REPORT CODE
    if 2 <= program.zone_number <= 8:
        keys.append(f"{program.hardwire_type.value}*")  # HARDWIRE TYPE (zones 2-8 only)
    if program.is_hardwired_prompt_zone:
        keys.append(f"{program.response_time.value}*")  # RESPONSE TIME (zones 1-8)
    else:
        keys.append("2*")  # INPUT TYPE: AW (aux wired) -- see module docstring scope note
    keys.append("0*")  # PROGRAM ALPHA? -- no
    keys.append("00*")  # exit back to ENTER ZN NUM, then to Data Field mode
    return "".join(keys)


class SystemTimingField(StrEnum):
    """A curated subset of numbered data fields covering exit/entry timing."""

    EXIT_DELAY = "34"
    ENTRY_DELAY_1 = "35"
    ENTRY_DELAY_2 = "36"
    AUTO_STAY_ARM = "84"


SYSTEM_TIMING_LABELS: dict[SystemTimingField, str] = {
    SystemTimingField.EXIT_DELAY: "Exit delay",
    SystemTimingField.ENTRY_DELAY_1: "Entry delay 1 (primary door)",
    SystemTimingField.ENTRY_DELAY_2: "Entry delay 2 (secondary door)",
    SystemTimingField.AUTO_STAY_ARM: "Auto-stay arm",
}

SYSTEM_TIMING_DESCRIPTIONS: dict[SystemTimingField, str] = {
    SystemTimingField.EXIT_DELAY: (
        "How many seconds you have to leave after arming before the exit "
        "delay ends. 0-96 seconds, or 97 for 120 seconds. Factory default "
        "is 60."
    ),
    SystemTimingField.ENTRY_DELAY_1: (
        "How many seconds you have to disarm after opening the primary "
        "entry door (zone type 'Entry/Exit (primary)'). 0-96 seconds, 97 "
        "for 120s, 98 for 180s, 99 for 240s. Factory default is 30."
    ),
    SystemTimingField.ENTRY_DELAY_2: (
        "Same as Entry Delay 1, but for zones set to 'Entry/Exit "
        "(secondary)'. Same value range. Factory default is 30."
    ),
    SystemTimingField.AUTO_STAY_ARM: (
        "If a delay zone is never opened during exit delay, the panel can "
        "assume you're staying home and automatically switch the arming "
        "mode to Stay. 0 = off, 1 = partition 1 only, 2 = partition 2 only, "
        "3 = both partitions. Factory default is 3 (both)."
    ),
}

# (min, max, special-values) for the two fields that share the 0-96 + extra
# codes shape; used by the guided UI to build a sane input control.
SYSTEM_TIMING_RANGES: dict[SystemTimingField, tuple[int, int, dict[int, str]]] = {
    SystemTimingField.EXIT_DELAY: (0, 96, {97: "120 seconds"}),
    SystemTimingField.ENTRY_DELAY_1: (
        0,
        96,
        {97: "120 seconds", 98: "180 seconds", 99: "240 seconds"},
    ),
    SystemTimingField.ENTRY_DELAY_2: (
        0,
        96,
        {97: "120 seconds", 98: "180 seconds", 99: "240 seconds"},
    ),
}


def build_system_timing_keystrokes(field: SystemTimingField, value: int) -> str:
    """Translate a numbered-data-field edit into its keystroke sequence.

    Numbered data fields (as opposed to *56-style menu modes) use the
    "go to field, enter value, [*] to end entry" pattern documented in the
    guide's PROGRAMMING MODE COMMANDS table.
    """
    if field == SystemTimingField.AUTO_STAY_ARM:
        if value not in (0, 1, 2, 3):
            raise ValueError("Auto-stay arm must be 0, 1, 2, or 3")
        return f"*{field.value}{value}"

    low, high, specials = SYSTEM_TIMING_RANGES[field]
    if value in specials:
        digits = f"{value:02d}"
    elif low <= value <= high:
        digits = f"{value:02d}"
    else:
        allowed = ", ".join(f"{k} ({v})" for k, v in specials.items())
        raise ValueError(f"{field.name} must be {low}-{high} seconds, or one of: {allowed}")
    return f"*{field.value}{digits}*"


class FunctionKeyLetter(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


# Mapping from letter to the digit the physical keypad uses to select it in
# *57 menu mode isn't documented as a plain digit in the guide (keys A-D are
# their own physical buttons) -- *57 prompts "PRESS KEY TO PGM" and expects
# the actual A/B/C/D key to be pressed. On the ECP keystroke encoding used
# by Envisalink's keystroke-string command, those map to the digits 1-4
# in the classic Ademco keypad numbering (A=1, B=2, C=3, D=4 position on a
# 4-button function row); if this turns out wrong against real hardware,
# it is the first thing to check (see README verification notes).
_FUNCTION_KEY_DIGIT: dict[FunctionKeyLetter, str] = {
    FunctionKeyLetter.A: "1",
    FunctionKeyLetter.B: "2",
    FunctionKeyLetter.C: "3",
    FunctionKeyLetter.D: "4",
}


class FunctionKeyAction(int, Enum):
    DEFAULT_EMERGENCY = 0
    SINGLE_BUTTON_PAGING = 1
    DISPLAY_TIME = 2
    ARM_AWAY = 3
    ARM_STAY = 4
    ARM_NIGHT_STAY = 5
    STEP_ARMING = 6
    OUTPUT_DEVICE_COMMAND = 7
    COMMUNICATION_TEST = 8


FUNCTION_KEY_ACTION_LABELS: dict[FunctionKeyAction, str] = {
    FunctionKeyAction.DEFAULT_EMERGENCY: "Default emergency key (fire/police/medical)",
    FunctionKeyAction.SINGLE_BUTTON_PAGING: "Page a number",
    FunctionKeyAction.DISPLAY_TIME: "Show the time",
    FunctionKeyAction.ARM_AWAY: "Arm Away",
    FunctionKeyAction.ARM_STAY: "Arm Stay",
    FunctionKeyAction.ARM_NIGHT_STAY: "Arm Night-Stay",
    FunctionKeyAction.STEP_ARMING: "Step-arm (Stay, then Night, then Away)",
    FunctionKeyAction.OUTPUT_DEVICE_COMMAND: "Trigger an output/relay",
    FunctionKeyAction.COMMUNICATION_TEST: "Send a communication test",
}


def build_function_key_keystrokes(
    key: FunctionKeyLetter, partition: int, action: FunctionKeyAction
) -> str:
    """Translate a function-key assignment into its *57 keystroke sequence."""
    if not 1 <= partition <= 3:
        raise ValueError(f"partition must be 1-3, got {partition}")
    key_digit = _FUNCTION_KEY_DIGIT[key]
    return (
        "*57"
        f"{key_digit}*"  # PRESS KEY TO PGM
        f"{partition}*"  # PARTITION
        f"{action.value:02d}*"  # KEY FUNC
        "0*00"  # exit function-key programming (0 to exit this mode)
    )


def build_program_mode_wrapper(installer_code: str, action_keystrokes: str) -> str:
    """Wrap any in-Program-Mode keystroke sequence with entry/exit.

    Always exits via *99 (normal exit, re-enterable), never *98 (the
    lockout exit) -- see const.py's EXIT_PROGRAM_MODE for why.
    """
    return f"{installer_code}{PROGRAM_MODE_SUFFIX}{action_keystrokes}{EXIT_PROGRAM_MODE}"


# ---------------------------------------------------------------------------
# The values the device page's config entities hold
# ---------------------------------------------------------------------------
# Every programming field is an entity on the panel device, and setting one
# only writes here: nothing reaches the panel until a button is pressed with
# the confirm switch on. Holding them in one mutable object rather than on the
# entities themselves means the button reads one consistent set of values, and
# an entity that has never been set is still None -- which is what lets the
# button name the field that is missing instead of programming a default.


@dataclass
class ProgrammingForm:
    """What the device page's programming entities currently hold.

    The three ``confirm`` flags mirror the three service fields of the same
    name. Every one of them is turned off again after a button press, so an
    authorization is spent on exactly one write attempt.
    """

    zone_number: int | None = None
    zone_type: int | None = None
    zone_partition: int | None = None
    zone_report_enabled: bool = True
    zone_hardwire_type: HardwireType = HardwireType.END_OF_LINE
    zone_response_time: ResponseTime = ResponseTime.MS_350
    timing_field: str | None = None
    timing_value: int | None = None
    # The service defaults this to 1 and only the commercial dialect reads it.
    timing_partition: int = 1
    function_key: FunctionKeyLetter | None = None
    function_key_action: FunctionKeyAction | None = None
    function_key_partition: int | None = None
    confirm: bool = False
    confirm_life_safety: bool = False
    confirm_unverified_model: bool = False

    def clear_confirmations(self) -> None:
        """Spend every confirmation. Called after every write attempt."""
        self.confirm = False
        self.confirm_life_safety = False
        self.confirm_unverified_model = False


class ProgrammingOutcome(StrEnum):
    """What became of the last press of a programming button."""

    SUCCESS = "success"
    """The panel acknowledged every keystroke of the sequence."""

    REFUSED = "refused"
    """A guard refused before anything was sent: no confirmation, a missing
    value, no installer code, an unsupported operation, a bad timing value."""

    FAILED = "failed"
    """The sequence was sent and the panel or the module rejected it, or the
    session dropped part-way. What reached the panel is unknown."""


@dataclass(frozen=True)
class ProgrammingResult:
    """The outcome of one button press, for the result sensor to report."""

    action: str
    outcome: ProgrammingOutcome
    detail: str
