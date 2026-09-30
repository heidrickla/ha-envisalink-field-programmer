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

Nothing in this module talks to the panel. It only describes what a field
means and, given validated values, what keystrokes express that meaning.
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

LIFE_SAFETY_ZONE_TYPE_CODES = frozenset(
    code for code, zt in ZONE_TYPES.items() if zt.life_safety
)


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


class ZoneDoubling(StrEnum):
    """What the entry's options say about zone doubling on the panel.

    Nothing over TPI shows it, and it decides which prompts zones 9-16 get,
    so an unstated value refuses those zones rather than guessing.
    """

    NOT_STATED = "not_stated"
    OFF = "off"
    ON = "on"


class ZoneConnection(StrEnum):
    """How a zone in the expansion range is connected, stated per press."""

    WIRED_EXPANDER = "wired_expander"
    WIRELESS = "wireless"


class ZoneKind(StrEnum):
    """Which *56 prompts follow REPORT CODE for a zone."""

    BOARD = "board"
    """HARDWIRE TYPE where the model offers it, then RESPONSE TIME."""

    DOUBLED = "doubled"
    """None: the base zone's wiring and response time apply."""

    AUX_WIRED = "aux_wired"
    """INPUT TYPE, answered 2 (AW)."""


# Zone doubling pairs board zone N (2-8) with zone N + 8, and module 1 of a
# zone expander (zones 9-16) cannot be used while it is on.
DOUBLED_ZONES = range(10, 17)
DOUBLING_AFFECTED_ZONES = range(9, 17)


@dataclass(frozen=True)
class VistaZoneLayout:
    """One residential model's zone numbering and *56 prompts, from its guide."""

    zones: str
    """The model's zone numbers as its guide lists them, for messages."""
    board_zones: range
    hardwire_prompt_zones: range
    hardwire_types: frozenset[HardwireType]
    expansion_zones: range
    aux_wired: bool
    """Expansion zones may be wired on a 4219/4229 expander (input type AW)."""
    button_zones: range
    partition_prompt: bool
    zone_doubling: bool


# K14488PRV3 (21iP) and the combined 15P/20P guide: zone 1 is always EOL, so
# HARDWIRE TYPE starts at zone 2; zone doubling and double-balanced wiring are
# 20P/21iP only, as is the PARTITION prompt.
VISTA_20P_21IP_ZONES = VistaZoneLayout(
    zones="1-8, 9-48, 49-64",
    board_zones=range(1, 9),
    hardwire_prompt_zones=range(2, 9),
    hardwire_types=frozenset(HardwireType),
    expansion_zones=range(9, 49),
    aux_wired=True,
    button_zones=range(49, 65),
    partition_prompt=True,
    zone_doubling=True,
)
VISTA_15P_ZONES = VistaZoneLayout(
    zones="1-6, 9-34, 49-56",
    board_zones=range(1, 7),
    hardwire_prompt_zones=range(2, 7),
    hardwire_types=frozenset(
        {
            HardwireType.END_OF_LINE,
            HardwireType.NORMALLY_CLOSED,
            HardwireType.NORMALLY_OPEN,
        }
    ),
    expansion_zones=range(9, 35),
    aux_wired=True,
    button_zones=range(49, 57),
    partition_prompt=False,
    zone_doubling=False,
)
# The 10P guide: HARDWIRE TYPE for zones 1-6 including zone 1, and its
# expansion zones take only RF and UR input types.
VISTA_10P_ZONES = VistaZoneLayout(
    zones="1-6, 9-24, 49-56",
    board_zones=range(1, 7),
    hardwire_prompt_zones=range(1, 7),
    hardwire_types=VISTA_15P_ZONES.hardwire_types,
    expansion_zones=range(9, 25),
    aux_wired=False,
    button_zones=range(49, 57),
    partition_prompt=False,
    zone_doubling=False,
)


class ZoneRefused(ValueError):
    """A zone the guided *56 sequence must not be sent for.

    Named like Home Assistant's translated exceptions so each raise carries a
    literal key the repository's validator checks against strings.json.
    """

    def __init__(
        self,
        *,
        translation_key: str,
        translation_placeholders: dict[str, str] | None = None,
    ) -> None:
        super().__init__(translation_key)
        self.translation_key = translation_key
        self.translation_placeholders = translation_placeholders or {}


@dataclass(frozen=True)
class ZoneProgram:
    """A validated, complete set of *56-equivalent settings for one zone."""

    zone_number: int  # 1-64
    zone_type: int  # key into ZONE_TYPES
    partition: int  # 1-3
    report_enabled: bool = True
    hardwire_type: HardwireType = HardwireType.END_OF_LINE
    response_time: ResponseTime = ResponseTime.MS_350
    connection: ZoneConnection | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.zone_number <= 64:
            raise ValueError(f"zone_number must be 1-64, got {self.zone_number}")
        if self.zone_type not in ZONE_TYPES:
            raise ValueError(f"unknown zone_type {self.zone_type}")
        if not 1 <= self.partition <= 3:
            raise ValueError(f"partition must be 1-3, got {self.partition}")


def classify_zone(
    layout: VistaZoneLayout, program: ZoneProgram, zone_doubling: ZoneDoubling
) -> ZoneKind:
    """Which prompts the panel will show for this zone, or ZoneRefused.

    The protocol cannot read the menu back, so a zone whose prompts are not
    known exactly is refused: one keystroke too many or too few answers the
    wrong question for everything after it.
    """
    zone = program.zone_number
    number = {"zone": str(zone)}
    if zone in layout.button_zones:
        raise ZoneRefused(
            translation_key="zone_is_button", translation_placeholders=number
        )
    if layout.zone_doubling and zone in DOUBLING_AFFECTED_ZONES:
        if zone_doubling is ZoneDoubling.NOT_STATED:
            raise ZoneRefused(
                translation_key="zone_doubling_not_stated",
                translation_placeholders=number,
            )
        if zone_doubling is ZoneDoubling.ON:
            if zone not in DOUBLED_ZONES:
                raise ZoneRefused(
                    translation_key="zone_unavailable_with_doubling",
                    translation_placeholders=number,
                )
            return ZoneKind.DOUBLED
    if zone in layout.board_zones:
        if zone in layout.hardwire_prompt_zones:
            _check_hardwire_type(layout, program.hardwire_type, zone_doubling)
        return ZoneKind.BOARD
    if zone in layout.expansion_zones:
        if not layout.aux_wired or program.connection is ZoneConnection.WIRELESS:
            raise ZoneRefused(
                translation_key="zone_is_wireless", translation_placeholders=number
            )
        if program.connection is None:
            raise ZoneRefused(
                translation_key="zone_connection_unset",
                translation_placeholders=number,
            )
        return ZoneKind.AUX_WIRED
    raise ZoneRefused(
        translation_key="zone_not_on_panel",
        translation_placeholders={**number, "zones": layout.zones},
    )


def _check_hardwire_type(
    layout: VistaZoneLayout, hardwire_type: HardwireType, zone_doubling: ZoneDoubling
) -> None:
    if hardwire_type not in layout.hardwire_types:
        raise ZoneRefused(
            translation_key="hardwire_type_not_on_model",
            translation_placeholders={"hardwire_type": hardwire_type.value},
        )
    doubling_on = zone_doubling is ZoneDoubling.ON
    if hardwire_type is HardwireType.ZONE_DOUBLING and not doubling_on:
        # Doubling a board zone takes zones 9-16 away from an expander, so it
        # is stated in the options first rather than changed from here.
        raise ZoneRefused(translation_key="hardwire_zone_doubling_off")


def build_zone_program_keystrokes(
    program: ZoneProgram, layout: VistaZoneLayout, zone_doubling: ZoneDoubling
) -> str:
    """Translate a ZoneProgram into the *56 menu-mode keystroke sequence.

    Raises ZoneRefused for a zone whose prompts are not known exactly. Does
    not include entering or exiting Program Mode; see
    build_program_mode_wrapper(). Every entry in *56 mode is followed by "*".
    """
    kind = classify_zone(layout, program, zone_doubling)
    keys = [ENTER_ZONE_PROGRAMMING]
    keys.append("0*")  # SET TO CONFIRM? -- no (not enrolling a wireless device)
    keys.append(f"{program.zone_number:02d}*")  # ENTER ZN NUM
    keys.append("*")  # accept SUMMARY SCREEN
    keys.append(f"{program.zone_type:02d}*")  # ZONE TYPE
    if layout.partition_prompt:
        keys.append(f"{program.partition}*")  # PARTITION
    keys.append(("1" if program.report_enabled else "00") + "*")  # REPORT CODE
    if kind is ZoneKind.BOARD:
        if program.zone_number in layout.hardwire_prompt_zones:
            keys.append(f"{program.hardwire_type.value}*")  # HARDWIRE TYPE
        keys.append(f"{program.response_time.value}*")  # RESPONSE TIME
    elif kind is ZoneKind.AUX_WIRED:
        keys.append("2*")  # INPUT TYPE: AW
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
        raise ValueError(
            f"{field.name} must be {low}-{high} seconds, or one of: {allowed}"
        )
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
    return (
        f"{installer_code}{PROGRAM_MODE_SUFFIX}{action_keystrokes}{EXIT_PROGRAM_MODE}"
    )


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
    # A statement about one zone, so it is spent with the confirmations.
    zone_connection: ZoneConnection | None = None
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
        """Spend every confirmation and the zone connection.

        Called after every write attempt.
        """
        self.confirm = False
        self.confirm_life_safety = False
        self.confirm_unverified_model = False
        self.zone_connection = None


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
