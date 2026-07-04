"""Constants for the Vista Console (Envisalink bridge) integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "vista_console"
PLATFORMS: Final = ["alarm_control_panel", "binary_sensor", "sensor", "switch"]

# Config entry keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_PASSWORD: Final = "password"
CONF_USER_CODE: Final = "user_code"
CONF_INSTALLER_CODE: Final = "installer_code"
CONF_NUM_PARTITIONS: Final = "num_partitions"
CONF_NUM_ZONES: Final = "num_zones"
CONF_ZONE_NAMES: Final = "zone_names"
CONF_KEEPALIVE_INTERVAL: Final = "keepalive_interval"

DEFAULT_PORT: Final = 4025
DEFAULT_NUM_PARTITIONS: Final = 1
DEFAULT_NUM_ZONES: Final = 8
DEFAULT_KEEPALIVE_INTERVAL: Final = 30
LOGIN_TIMEOUT: Final = 10
COMMAND_ACK_TIMEOUT: Final = 5
RECONNECT_BACKOFF_MIN: Final = 5
RECONNECT_BACKOFF_MAX: Final = 300

# ---------------------------------------------------------------------------
# TPI wire protocol
# ---------------------------------------------------------------------------
# Field schema for every command/event the panel/EVL can *send to us*.
# Maps a 3-digit command code to an ordered list of (field_name, length)
# tuples describing how to slice the data portion of the frame.
# Source: EnvisaLink TPI Programmer's Document v1.08 (2017-02-10), section 3.3.
COMMAND_SCHEMA: Final[dict[str, list[tuple[str, int]]]] = {
    "500": [("ack_code", 3)],
    "501": [],
    "502": [("error_code", 3)],
    "505": [("status", 1)],
    "510": [("led_state", 2)],
    "511": [("led_flash_state", 2)],
    "550": [("time", 10)],
    "560": [],
    "561": [("thermostat", 1), ("temperature", 3)],
    "562": [("thermostat", 1), ("temperature", 3)],
    "601": [("partition", 1), ("zone", 3)],
    "602": [("partition", 1), ("zone", 3)],
    "603": [("partition", 1), ("zone", 3)],
    "604": [("partition", 1), ("zone", 3)],
    "605": [("zone", 3)],
    "606": [("zone", 3)],
    "609": [("zone", 3)],
    "610": [("zone", 3)],
    "615": [("zone_timers", 256)],
    "616": [("bypass_bitfield", 16)],
    "620": [("reserved", 4)],
    "621": [], "622": [], "623": [], "624": [], "625": [], "626": [],
    "631": [], "632": [],
    "650": [("partition", 1)],
    "651": [("partition", 1)],
    "652": [("partition", 1), ("mode", 1)],
    "653": [("partition", 1)],
    "654": [("partition", 1)],
    "655": [("partition", 1)],
    "656": [("partition", 1)],
    "657": [("partition", 1)],
    "658": [("partition", 1)],
    "659": [("partition", 1)],
    "660": [("partition", 1)],
    "663": [("partition", 1)],
    "664": [("partition", 1)],
    "670": [("partition", 1)],
    "671": [("partition", 1)],
    "672": [("partition", 1)],
    "673": [("partition", 1)],
    "674": [("partition", 1)],
    "680": [],
    "700": [("partition", 1), ("user", 4)],
    "701": [("partition", 1)],
    "702": [("partition", 1)],
    "750": [("partition", 1), ("user", 4)],
    "751": [("partition", 1)],
    "800": [], "801": [], "802": [], "803": [],
    "806": [], "807": [],
    "814": [], "815": [], "816": [],
    "829": [], "830": [],
    "840": [("partition", 1)],
    "841": [("partition", 1)],
    "842": [], "843": [],
    "849": [("trouble_bits", 2)],
    "900": [],
    "912": [("partition", 1), ("command", 1)],
    "921": [],
    "922": [],
}

# Human-readable names for logging/diagnostics/entity attributes.
COMMAND_NAMES: Final[dict[str, str]] = {
    "500": "command_acknowledge",
    "501": "command_error",
    "502": "system_error",
    "505": "login_interaction",
    "510": "keypad_led_state",
    "511": "keypad_led_flash_state",
    "550": "time_date_broadcast",
    "560": "ring_detected",
    "561": "indoor_temperature",
    "562": "outdoor_temperature",
    "601": "zone_alarm",
    "602": "zone_alarm_restore",
    "603": "zone_tamper",
    "604": "zone_tamper_restore",
    "605": "zone_fault",
    "606": "zone_fault_restore",
    "609": "zone_open",
    "610": "zone_restored",
    "615": "zone_timer_dump",
    "616": "bypassed_zones_bitfield",
    "620": "duress_alarm",
    "621": "fire_key_alarm",
    "622": "fire_key_restore",
    "623": "aux_key_alarm",
    "624": "aux_key_restore",
    "625": "panic_key_alarm",
    "626": "panic_key_restore",
    "631": "two_wire_smoke_alarm",
    "632": "two_wire_smoke_restore",
    "650": "partition_ready",
    "651": "partition_not_ready",
    "652": "partition_armed",
    "653": "partition_ready_force_arm",
    "654": "partition_in_alarm",
    "655": "partition_disarmed",
    "656": "exit_delay_in_progress",
    "657": "entry_delay_in_progress",
    "658": "keypad_lockout",
    "659": "partition_failed_to_arm",
    "660": "pgm_output_in_progress",
    "663": "chime_enabled",
    "664": "chime_disabled",
    "670": "invalid_access_code",
    "671": "function_not_available",
    "672": "failure_to_arm",
    "673": "partition_busy",
    "674": "system_arming_in_progress",
    "680": "system_in_installers_mode",
    "700": "user_closing",
    "701": "special_closing",
    "702": "partial_closing",
    "750": "user_opening",
    "751": "special_opening",
    "800": "panel_battery_trouble",
    "801": "panel_battery_trouble_restore",
    "802": "panel_ac_trouble",
    "803": "panel_ac_restore",
    "806": "system_bell_trouble",
    "807": "system_bell_trouble_restore",
    "814": "ftc_trouble",
    "815": "ftc_trouble_restore",
    "816": "buffer_near_full",
    "829": "general_system_tamper",
    "830": "general_system_tamper_restore",
    "840": "trouble_led_on",
    "841": "trouble_led_off",
    "842": "fire_trouble_alarm",
    "843": "fire_trouble_alarm_restore",
    "849": "verbose_trouble_status",
    "900": "code_required",
    "912": "command_output_pressed",
    "921": "master_code_required",
    "922": "installers_code_required",
}

# Arm mode reported in command 652's "mode" field.
ARM_MODE_AWAY = "0"
ARM_MODE_STAY = "1"
ARM_MODE_ZERO_ENTRY_AWAY = "2"
ARM_MODE_ZERO_ENTRY_STAY = "3"

# 502 System Error codes worth surfacing distinctly.
ERROR_KEYBUS_BUSY_INSTALLERS_MODE = "17"

# Zone/partition/system events that mean "this partition entered installer's
# programming mode" -- the single most important safety signal in this whole
# integration. See section 3.6 of the TPI doc: getting stuck here may require
# a physical power cycle of the panel, and while in this mode most commands,
# including disarm, are locked out.
INSTALLERS_MODE_EVENT_CODES: Final = {"680"}

# ---------------------------------------------------------------------------
# Vista field-programming ("*56" etc.) keystroke conventions
# ---------------------------------------------------------------------------
# Source: ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3 10/12
# Rev B ("PROGRAMMING MODE COMMANDS" table and per-field sections).
#
# IMPORTANT correctness note: an earlier version of this integration's
# keystroke guard blocked any sequence containing "*8", based on a generic
# warning in the EnvisaLink TPI spec about "installer mode" that reads as
# DSC-flavored boilerplate. On a real Vista panel there is no "*8" menu at
# all. The actual sequence that opens Program Mode (equivalent to physically
# standing at the keypad and being able to edit every data field/zone/output
# on the panel) is:
#
#       <installer code> 8 0 0
#
# e.g. "4112800" with the factory-default installer code. That is the
# sequence this integration actually needs to guard, not "*8".
PROGRAM_MODE_SUFFIX: Final = "800"
# Exit Program Mode normally (re-enterable via installer code or the
# power-up method). Deliberately never uses *98 (the "lockout" exit), which
# can only be undone by a physical power cycle -- see the guide's own
# PROGRAMMING MODE COMMANDS table.
EXIT_PROGRAM_MODE: Final = "*99"
ENTER_ZONE_PROGRAMMING: Final = "*56"
ENTER_FUNCTION_KEY_PROGRAMMING: Final = "*57"

ATTR_PARTITION = "partition"
ATTR_ZONE = "zone"
