"""Constants for the Envisalink Field Programmer integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "envisalink_field_programmer"
PLATFORMS: Final = ["alarm_control_panel", "binary_sensor", "sensor", "switch"]

# Config entry keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_PASSWORD: Final = "password"
CONF_USER_CODE: Final = "user_code"
CONF_INSTALLER_CODE: Final = "installer_code"
CONF_PANEL_MODEL: Final = "panel_model"
CONF_NUM_PARTITIONS: Final = "num_partitions"
CONF_NUM_ZONES: Final = "num_zones"
CONF_ZONE_NAMES: Final = "zone_names"
CONF_KEEPALIVE_INTERVAL: Final = "keepalive_interval"

DEFAULT_PORT: Final = 4025
# The panel this integration was originally built and hardware-tested against;
# the default so existing installs and single-panel users are unaffected.
DEFAULT_PANEL_MODEL: Final = "vista_21ip"
DEFAULT_NUM_PARTITIONS: Final = 1
DEFAULT_NUM_ZONES: Final = 8
DEFAULT_KEEPALIVE_INTERVAL: Final = 30
# How often to re-request the %FF zone timer dump -- the only authoritative
# source of zone open/closed state over this protocol (see state_machine.py).
ZONE_TIMER_DUMP_INTERVAL: Final = 30
LOGIN_TIMEOUT: Final = 10
COMMAND_ACK_TIMEOUT: Final = 5
# Retries for a command the EVL rejects with "Receive Buffer Overrun" (it
# was still busy processing the previous command -- e.g. still clocking a
# keypress onto the keybus). Delay doubles each attempt.
COMMAND_RETRY_ATTEMPTS: Final = 3
COMMAND_RETRY_DELAY: Final = 0.25
RECONNECT_BACKOFF_MIN: Final = 5
RECONNECT_BACKOFF_MAX: Final = 300

# ---------------------------------------------------------------------------
# TPI wire protocol -- Honeywell/Ademco Envisalink (EVL-3/EVL-4)
# ---------------------------------------------------------------------------
# CORRECTNESS NOTE: an earlier version of this file was built from the
# "EnvisaLink TPI Programmer's Document v1.08" PDF, which describes a
# hex-ASCII, checksum-framed protocol with 3-digit numeric command codes.
# That does not match what a real EVL-4 + VISTA-21iP actually speaks --
# confirmed directly against live hardware (see DEVELOPMENT.md). The real
# protocol, verified against both the live device and the actively
# maintained `pyenvisalink` library (bundled with the `envisalink_new` HACS
# integration, which is confirmed working against this exact hardware), is:
#
#   1. Login is plain text, not a framed command: the EVL sends the literal
#      string "Login:", the client replies with just the password (no
#      username), and the EVL replies "OK", "FAILED", or "Timed Out!".
#   2. Every message after that is framed as "%CODE,DATA$" (EVL -> client)
#      or "^CODE,DATA$" (client -> EVL), terminated by "$" -- there is no
#      checksum at all.
#   3. Keystrokes are sent one character at a time via "^03,<partition>,
#      <char>$", not bundled into multi-character frames.
#   4. Arming/disarming is done by sending the user code followed by a mode
#      digit as keystrokes (e.g. code + "2" for away), not a dedicated
#      command code -- matching how a physical keypad works.
LOGIN_PROMPT: Final = "Login:"
LOGIN_SUCCESS: Final = "OK"
LOGIN_FAILURE: Final = "FAILED"
LOGIN_TIMEOUT_MESSAGE: Final = "Timed Out!"

FRAME_SENTINELS: Final = "%^"
FRAME_TERMINATOR: Final = "$"

# Outbound command codes (sent as "^<code>,<data>$").
CMD_POLL: Final = "00"
CMD_CHANGE_DEFAULT_PARTITION: Final = "01"
CMD_DUMP_ZONE_TIMERS: Final = "02"
CMD_KEYPRESS: Final = "03"

# Inbound event codes (sent as "%<code>,<data>$" for panel-initiated
# updates, or "^<code>,<data>$" as an acknowledgement of a command we sent
# with that same code).
EVT_KEYPAD_UPDATE: Final = "%00"
EVT_ZONE_STATE_CHANGE: Final = "%01"
EVT_PARTITION_STATE_CHANGE: Final = "%02"
EVT_REALTIME_CID_EVENT: Final = "%03"
EVT_DEBUG_MESSAGE: Final = "%20"
EVT_ZONE_TIMER_DUMP: Final = "%FF"

# Response codes the EVL sends back as "^<code>,<response>$" after every
# command. Taken from the reference `pyenvisalink` Honeywell response table
# (verified working against this same hardware); the EVL processes exactly
# one command at a time and answers 01 if a new one arrives while the
# previous is still being processed.
RESPONSE_ACCEPTED: Final = "00"
RESPONSE_BUFFER_OVERRUN: Final = "01"
TPI_RESPONSE_CODES: Final[dict[str, str]] = {
    "00": "Command Accepted",
    "01": "Receive Buffer Overrun (command received while another is still being processed)",
    "02": "Unknown Command",
    "03": "Syntax Error (data appended to the command is incorrect)",
}

COMMAND_NAMES: Final[dict[str, str]] = {
    EVT_KEYPAD_UPDATE: "keypad_update",
    EVT_ZONE_STATE_CHANGE: "zone_state_change",
    EVT_PARTITION_STATE_CHANGE: "partition_state_change",
    EVT_REALTIME_CID_EVENT: "realtime_cid_event",
    EVT_DEBUG_MESSAGE: "debug_message",
    EVT_ZONE_TIMER_DUMP: "zone_timer_dump",
    "^00": "poll_ack",
    "^01": "change_default_partition_ack",
    "^02": "dump_zone_timers_ack",
    "^03": "keypress_ack",
    "^0C": "invalid_command_ack",
}

# Icon-LED bit flags carried in the %00 keypad update's second data field
# (a 16-bit value, sent as up to 4 hex digits). Order matches the real
# device's bit layout (verified against pyenvisalink's IconLED_Bitfield),
# not the EnvisaLink TPI PDF's unrelated LED-state command.
ICON_LED_BITS: Final[dict[str, int]] = {
    "alarm": 0,
    "alarm_in_memory": 1,
    "armed_away": 2,
    "ac_present": 3,
    "bypass": 4,
    "chime": 5,
    "armed_zero_entry_delay": 7,
    "alarm_fire_zone": 8,
    "system_trouble": 9,
    "ready": 12,
    "fire": 13,
    "low_battery": 14,
    "armed_stay": 15,
}

# Zone/partition/system events that mean "this partition entered installer's
# programming mode". While in this mode most commands, including disarm,
# are locked out, and getting stuck may require a physical power cycle.
# This protocol has no dedicated event for it (unlike the incorrect PDF's
# "680" code); it shows up as CID event 627 ("Program Mode Entry") via
# EVT_REALTIME_CID_EVENT, which is how the coordinator detects it.
INSTALLERS_MODE_CID_EVENT: Final = 627
INSTALLERS_MODE_EXIT_CID_EVENT: Final = 628

# CID "qualifier" digit (the first data field of a %03 event): 1 means a new
# event/opening (e.g. a disarm), 3 means a new restore/closing (e.g. an
# arm). 6 means "condition still present" and isn't a state transition.
CID_QUALIFIER_OPENING: Final = "1"
CID_QUALIFIER_CLOSING: Final = "3"

# CID event codes that represent an arm or disarm action by a user (used to
# decide whether to update last_armed_by_user/last_disarmed_by_user).
ARM_DISARM_CID_EVENTS: Final = {401, 403, 407, 408, 409, 441, 442}

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

# ---------------------------------------------------------------------------
# DSC PowerSeries programming conventions (section-based, not *56 field menus)
# ---------------------------------------------------------------------------
# DSC opens installer programming with "*8" followed by the installer code
# (factory default 5555), navigates by 3-digit section number, and exits by
# keying out with "#". See panels/dsc.py for the full grammar and the honest
# per-model verification caveats. Kept here alongside the Vista constants so
# the two families' program-mode triggers live in one place.
DSC_PROGRAM_MODE_PREFIX: Final = "*8"
DSC_EXIT_PROGRAM_MODE: Final = "##"

ATTR_PARTITION = "partition"
ATTR_ZONE = "zone"
