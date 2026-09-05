# Envisalink Field Programmer

[![CI](https://github.com/heidrickla/ha-envisalink-field-programmer/actions/workflows/ci.yml/badge.svg)](https://github.com/heidrickla/ha-envisalink-field-programmer/actions/workflows/ci.yml)
[![Tests](https://github.com/heidrickla/ha-envisalink-field-programmer/actions/workflows/tests.yml/badge.svg)](https://github.com/heidrickla/ha-envisalink-field-programmer/actions/workflows/tests.yml)
[![HACS](https://img.shields.io/badge/HACS-custom-orange.svg)](https://hacs.xyz)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A standalone Home Assistant custom integration for a Honeywell/Ademco **VISTA**
alarm panel, bridged locally over an **EyezOn Envisalink** (EVL-3/EVL-4)
module. No cloud, no Total Connect: your panel's keybus, your LAN, and Home
Assistant.

Envisalink Field Programmer talks the Envisalink **TPI** (Third Party
Interface) protocol directly over TCP (port 4025) with its own asyncio client.
It does not depend on `pyenvisalink` or any other integration.

## Why this exists (and how it relates to `envisalink_new`)

[`ufodone/envisalink_new`](https://github.com/ufodone/envisalink_new) is a
mature, actively maintained HACS integration that already covers arm/disarm,
zone/partition status, and bypass switches for both DSC and Honeywell panels
well. If all you want is basic alarm control, use that one.

This integration's reason to exist is **guided installer field programming**:
a structured, plain-language layer over Vista's `*56`/`*57` keypad
programming language (zone types, entry/exit timing, function keys), with
strong confirmation gates given the fire/UL-safety stakes of getting installer
programming wrong. Nothing else exposes this through Home Assistant today.
Arm/disarm/status/zone entities and a Lovelace console card come along for the
ride, but the programming layer is the point.

Typical uses:

- Retype a zone (say, a former window contact now on a motion detector) from
  the Home Assistant UI instead of at the keypad, with the zone type chosen by
  name rather than by remembering that Perimeter is 3.
- Change the exit delay for a season, or assign a keypad function key, as a
  scripted, repeatable action.
- Arm, disarm, watch zones and bypass one for the night, all locally.

## Features

- Config flow setup (host, port, password, panel model, default user code,
  zone and partition counts); an optional installer code, set later in the
  integration's options, turns on field programming. Panel model defaults to
  the VISTA-21iP; see [Panel model support](#panel-model-support) for the
  full model list and what each one's support level means.
- **DHCP discovery**: an Envisalink that takes a lease is offered with its
  address filled in, and one that later moves takes its entry with it. See
  [Discovery](#discovery).
- **Reconfigure** without losing the entry: address, password, panel model
  and the zone and partition counts. See [Reconfiguring](#reconfiguring).
- One `alarm_control_panel` entity per partition: arm away/home/night, disarm.
- One `binary_sensor` per zone (open/closed), plus per-zone `switch` entities
  for bypass (disabled by default in the entity registry; enable the ones you
  want).
- A system trouble `binary_sensor` (AC power, low battery, general trouble per
  partition, plus installer mode), filed as a diagnostic entity.
- Diagnostic sensors: last user to arm or disarm each partition, and the last
  raw panel event (disabled by default: it changes on every keepalive
  acknowledgement, so enable it only while debugging the protocol).
- A repair issue when the Envisalink stops answering for several minutes,
  naming the usual cause: another client holding its single TPI session.
- **Guided field-programming actions** `program_zone`, `set_system_timing`
  and `program_function_key`, plus the lower-level `send_keystrokes` and
  `toggle_zone_bypass`; see [Actions](#actions) and [Safety](#safety-read-this).
- Diagnostics download (Settings, Devices & services, Envisalink Field
  Programmer, Download diagnostics) with the password and both codes
  redacted; see [Backups](#backups-what-this-can-and-cant-capture).
- A custom `envisalink-field-programmer-card` Lovelace card, registered on
  setup with no manual resource step, with guided Zone/Timing/Function-Key
  tabs and a raw-keystroke escape hatch.

## Installation

**HACS (custom repository):** add this repository as a custom repository
(category Integration), then install "Envisalink Field Programmer". Home
Assistant **2026.3 or newer**. Two things need that release: the DHCP
discovery helper the config flow imports (2025.2), and the brands component
that serves an integration's own `brand/` directory (2026.3). This
integration ships its icon and logo in
`custom_components/envisalink_field_programmer/brand/` and is in no brands
repository, so on anything older it would load with no icon anywhere in the
interface.

**Manual:** copy `custom_components/envisalink_field_programmer/` into your
Home Assistant `config/custom_components/` directory and restart.

Then: Settings, Devices & services, Add integration, "Envisalink Field
Programmer".

### Installation parameters

| Field | Required | Description |
|---|---|---|
| Host | yes | The Envisalink's IP address or hostname on your LAN. A DHCP reservation is still the tidiest arrangement, but a changed address no longer means starting over: see [Discovery](#discovery) and [Reconfiguring](#reconfiguring). |
| Port | yes | The TPI port, 4025 unless you changed it on the Envisalink's web page. |
| Envisalink password | yes | The password for the Envisalink's local web page. Not a panel code. |
| Alarm panel model | yes | The panel behind the Envisalink. Sets the zone and partition limits and, for field programming, which keystroke grammar is used and how much of it is verified. Defaults to VISTA-21iP. |
| Default user code | no | A panel user code Home Assistant types to arm and disarm when a call supplies none. Blank means every arm and disarm needs a code. Read the [Safety](#safety-read-this) note on what a default code means. |
| Number of partitions | yes | Partitions configured on the panel, 1 to 8 within the model's limit. One alarm control panel entity per partition. |
| Number of zones | yes | Zones to create sensors for, 1 to 250 within the model's limit. Unused zones stay closed. |

The flow logs in to the Envisalink before creating the entry, so a wrong
password ("The Envisalink rejected that password") or a busy or unreachable
port ("Could not connect") is caught on the form.

### Options

Settings, Devices & services, Envisalink Field Programmer, Configure.

| Field | Description |
|---|---|
| Default user code | Replaces the stored default user code. Blank keeps the stored code. |
| Remove the stored default user code | Clears it, so every arm and disarm needs a code again. |
| Installer code | Enables field programming. Every guided action types this code followed by `800` to open Program Mode. Blank keeps the stored code. |
| Remove the stored installer code | Clears it and disables field programming. |
| Keepalive interval | Seconds between keepalive polls that detect a silently dead connection, 10 to 300, default 30. Zone state is refreshed every 30 seconds regardless. |

The stored codes are never shown in the form, only whether one is set.
Saving the options reloads the entry.

### Discovery

Envisalink modules carry a MAC address from `00:1C:2A`, the block the IEEE
registry assigns to Envisacor Technologies Inc., who make them. When one takes
a DHCP lease, Home Assistant offers it under Settings, Devices & services as a
discovered device with its address already filled in. Nothing is created
automatically: the Envisalink password still has to be typed, and the rest of
the form is the ordinary setup form.

Setting an entry up from a discovery also stores the module's MAC with it,
which is the only way this integration can ever know one. TPI reports no
serial number and no MAC of its own, so without that a module that reappears
at a new address is indistinguishable from a second module. With it:

- A lease at a new address for a stored MAC moves that entry. The host, the
  unique id and the entry title follow, and the entry reloads. Nothing else
  has to be touched.
- An entry set up by hand at an address that later shows up in a lease adopts
  the MAC at that point, so the first move after that is handled too.

The device page also links to the Envisalink's own web page, which is where
its password, network settings and firmware live.

### Reconfiguring

Settings, Devices & services, Envisalink Field Programmer, the three-dot menu
on the entry, Reconfigure. The entry keeps its entities, its history and its
entity ids, except for the zones and partitions dropped by lowering a count,
which are described below the table.

| Field | Description |
|---|---|
| Host | The Envisalink's current address. Changing it moves the entry there. |
| Port | The TPI port, 4025 unless you changed it on the Envisalink's web page. |
| Envisalink password | Blank keeps the stored password. Type one only to change it. |
| Alarm panel model | The panel behind the Envisalink; sets the zone and partition limits and the field-programming grammar. |
| Number of partitions | Lowering this deletes the entities of the partitions above it when the entry reloads. |
| Number of zones | Lowering this deletes the entities of the zones above it when the entry reloads. |

The counts are checked against the selected model before anything is dialled,
and the login is proved at the new address before the entry is changed. An
address another entry already uses is refused. The default user code and the
installer code are not touched here; they live in the options.

Lowering a count reloads the entry, and setup then deletes the registry
entries for the zones or partitions above the new count: the zone sensor and
its bypass switch, or the alarm control panel and its Last User sensor. Home
Assistant would otherwise keep them forever as unavailable entities, because
an entity that is simply no longer added is never removed on its own. Anything
below the new count, and the entities that are not numbered, are untouched.
Raising the count again creates the entities fresh; they take the same entity
ids unless something else has claimed them in the meantime.

### The Envisalink only accepts one TPI client at a time

Confirmed against real hardware: if `envisalink_new` (or any other
integration or app already talking TPI to this Envisalink) is connected,
setting up this integration against the same device fails with "Could not
connect to the Envisalink at that host and port", not because the host, port
or password are wrong, but because the Envisalink's TPI server (port 4025)
refuses a second simultaneous connection outright. This is a
hardware/firmware limit, not a bug in either integration.

If you hit that error and you are sure your connection details are correct,
check whether another integration already holds the connection (Settings,
Devices & services, find it, confirm it is enabled) and disable it first. The
two integrations cannot both be connected at the same time, so plan your
setup around whichever one you want active day to day (for example keep
`envisalink_new` enabled for daily zone and arm status, and only temporarily
disable it and enable this one when you need to do field programming).

### Removing the integration

1. Settings, Devices & services, Envisalink Field Programmer, the three-dot
   menu on the entry, Delete. This closes the TPI session (freeing the
   Envisalink's single client slot for whatever you use next), removes the
   device and every entity, deletes the stored password and codes with the
   entry, and takes any repair issue it raised with it.
2. If you installed through HACS, remove the repository from HACS as well;
   for a manual install delete `custom_components/envisalink_field_programmer/`
   and restart Home Assistant.
3. The Lovelace card resource is registered at runtime, so nothing is left in
   your dashboard resources; any card you placed on a dashboard shows as a
   missing custom element until you delete it.

Nothing is written to the panel by installing or removing the integration.

## How it updates

The connection is push-driven (`local_push`): the integration keeps one TCP
session open to the Envisalink and updates entities the moment the panel
reports a change (keypad updates, partition state, CID events). Two things
run on a timer because the protocol offers nothing better:

- A **keepalive poll** every 30 seconds (adjustable in the options), purely
  to notice a silently dead connection.
- A **zone timer dump** request every 30 seconds, the only source of zone
  open/closed state a Honeywell panel gives over TPI. Zone sensors are
  therefore up to 30 seconds behind a door; partition state is immediate.

When the session drops, every entity becomes unavailable, one line is logged
at info level, and the integration reconnects with a backoff that starts at
5 seconds and caps at 5 minutes. When it is back, one more line is logged and
zone state is refreshed. If the Envisalink rejects the stored password, the
entry asks you to re-authenticate instead of retrying.

After five failed reconnects, about two and a half minutes, a repair issue
appears under Settings, System, Repairs. It names the address and the usual
cause, which is another client holding the Envisalink's single TPI session,
and it clears itself as soon as the connection comes back.

## Field programming

Three guided actions, each translating validated, structured input into the
exact keystroke sequence Vista expects (see
`custom_components/envisalink_field_programmer/field_programming.py`, built
from the ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3):

- **`envisalink_field_programmer.program_zone`**: zone type (offered as
  plain-language options like "Perimeter (instant)" or "Fire (smoke/heat
  detector)", not raw Vista field numbers), partition, reporting and wiring
  settings for one zone.
- **`envisalink_field_programmer.set_system_timing`**: exit delay, entry
  delay 1/2, and auto-stay-arm.
- **`envisalink_field_programmer.program_function_key`**: assign the keypad's
  A/B/C/D function keys.

This is deliberately a **curated subset**, not the full installer field set.
Output/relay programming (`*79`/`*80`/`*81`), alpha descriptors (`*82`), and
the installer-only configurable zone types (90/91) are out of scope. A
smaller, clearly explained set of settings beats a full field dump nobody can
safely reason about. The guided Lovelace card tabs (Zones, Timing, Function
Keys) are the intended way to use this; the actions exist so the same logic
is scriptable.

**Every one of these always opens the panel's installer Program Mode**
(typing the installer code followed by `800`), which is why they require an
installer code configured and a `confirm: true` field; see
[Safety](#safety-read-this).

## Safety (read this)

Opening Vista's installer Program Mode gives access to every data field on
the panel, including fire-zone and UL-listing-relevant settings, and once
inside, most functions (including disarm) are unavailable until you exit.
Badly, that can mean a physical power cycle. Two important specifics:

- **Program Mode opens via `<installer code>800`** (for example `4112800`
  with the factory-default code), not a DSC-style `*8` sequence. An earlier
  version of this integration's guard blocked `*8`, based on a generic
  warning in the Envisalink TPI spec that turns out to describe DSC panels,
  not Vista; there is no `*8` menu on a real Vista panel at all. This was
  corrected once the Vista programming guide was checked directly; see
  `programming.py`'s module docstring.
- **The TPI protocol cannot read back what is on the keypad display.** Every
  field-programming action here is genuinely blind: if a keystroke sequence
  has a bug, or the panel is in an unexpected state, there is no channel to
  detect it before it is too late. The guided actions show you the field
  values you are setting before sending (via the Lovelace card's form), but
  cannot show you what the panel is doing in response.

Given that, this integration:

- Routes **every** keystroke send, raw or guided, through a single guard
  (`custom_components/envisalink_field_programmer/programming.py`) that
  refuses any sequence matching the Program Mode trigger unless explicitly
  confirmed.
- Requires the three guided actions' `confirm: true` field on every call
  (they always open Program Mode by design), plus an additional
  `confirm_life_safety: true` on `program_zone` whenever the target zone type
  is fire or CO, because this integration cannot verify what a zone's current
  type is before overwriting it.
- Never exposes raw keystrokes from the Lovelace card's normal UI. The guided
  tabs are the default; a separate "Raw" tab exists for anything they do not
  cover, gated by its own confirmation checkbox.
- Treats zone bypass (`toggle_zone_bypass`, `*1zz#`) as the one keystroke
  sequence that is always allowed without confirmation, because it is an
  ordinary end-user keypad function that never opens Program Mode.
- Never logs the installer code, the user code or the Envisalink password,
  redacts them in diagnostics, and masks any run of four or more digits in a
  guard error before it reaches the log or the card.

**A default user code changes who can disarm.** A real Vista panel disarms by
typing a user code; with a default user code stored, the alarm control panel
entity disarms **without asking anyone for a code**. Anyone who can call
`alarm_control_panel.alarm_disarm` in your Home Assistant (any user, any
automation, any exposed voice assistant) can then disarm the panel. Leave the
default code blank if that is not acceptable; every arm and disarm then needs
the code on the call. The stored codes live in Home Assistant's config entry
store in plain text, like every integration's credentials, so back that store
up accordingly.

If you do not need field programming, ignore it entirely and do not configure
an installer code. Arm, disarm, status and zone bypass never touch any of
this.

## Backups: what this can and can't capture

Home Assistant's standard **Download diagnostics** button (on this
integration's entry) captures a timestamped JSON snapshot of everything Home
Assistant currently knows: partition, zone and system state, armed mode, open
and bypassed zones, trouble flags, last user. Grab one before you experiment
with field programming.

**What it cannot capture: the panel's actual installer field programming**
(zone types, entry/exit delays, alpha descriptors, output/relay assignments,
communicator settings). The TPI protocol has no command that reads that data
back; it only exposes live status events (icon-LED keypad state, realtime CID
events, the zone timer dump), never the underlying `*56`/`*58`/`*79`/`*80`/
`*82`-style configuration fields. To back up your panel's programming you
need to either:

- Walk each installer menu field at the keypad and record it by hand, or
- Use a Honeywell-side tool (Compass Downloader, Total Connect installer
  access) if you have access to one.

Be skeptical of any tool that claims to "read back" Vista programming over a
keypad-emulation link like this one; as far as the TPI protocol is concerned,
that data does not come back over the wire.

## Actions

Every action takes an `entry_id`, the config entry it should drive. In the
UI the config entry picker fills it in. In YAML, every entity from this
integration carries a `config_entry_id` attribute, so
`{{ state_attr('alarm_control_panel.envisalink_field_programmer_192_168_1_50_partition', 'config_entry_id') }}`
resolves it without copying an id by hand.

Calling an action while the entry is not loaded, or with an id no entry has,
is refused with a clear message rather than failing silently. Refusals for
bad input (an unsupported panel, a missing installer code, a guarded
sequence) are validation errors and carry no traceback; a command the
Envisalink refuses or never acknowledges is reported as a device error.

### `envisalink_field_programmer.send_keystrokes`

Send a raw ECP keystroke string to a partition, as if typed on a keypad.
Refused if the sequence looks like it opens installer Program Mode unless
`confirm_installer_risk` is true. Prefer the guided actions; this is for
anything they do not cover.

| Field | Required | Description |
|---|---|---|
| `entry_id` | yes | Config entry to send to. |
| `partition` | yes | Partition number, 1 to 8. |
| `keys` | yes | Keystrokes: digits, `*` and `#` only. |
| `confirm_installer_risk` | no, default `false` | Must be `true` to send a sequence that opens Program Mode. |

### `envisalink_field_programmer.toggle_zone_bypass`

Bypass or un-bypass a single zone with the standard `*1zz#` keypad sequence.
Never opens Program Mode and needs no installer code. The resulting
`bypassed` state is set optimistically, since the panel does not acknowledge
which zone was bypassed; it clears when the partition's bypass flag clears.

| Field | Required | Description |
|---|---|---|
| `entry_id` | yes | Config entry that owns the zone. |
| `zone` | yes | Zone number, 1 to 64. |

### `envisalink_field_programmer.program_zone`

Guided zone programming (the `*56` menu): set one zone's type, partition,
reporting and wiring. Always opens Program Mode, so an installer code must be
configured and `confirm` must be true. Available on the residential VISTA
models; the commercial VISTA and DSC models refuse it (see
[Panel model support](#panel-model-support)).

| Field | Required | Description |
|---|---|---|
| `entry_id` | yes | Config entry that owns the zone. |
| `zone_number` | yes | Zone number, 1 to 64. |
| `zone_type` | yes | Vista zone type code: `0` Not used, `1` Entry/Exit (primary), `2` Entry/Exit (secondary), `3` Perimeter (instant), `4` Interior (follower), `6` Panic (silent), `7` Panic (audible), `8` Auxiliary 24-hour, `9` Fire (smoke/heat), `10` Interior with delay, `12` Monitor (trouble only), `14` Carbon monoxide, `16` Fire with verification, `23` No alarm response, `24` Silent burglary. |
| `partition` | yes | Partition the zone belongs to, 1 to 3 (the `*56` menu takes one digit, 1 to 3). |
| `report_enabled` | no, default `true` | Whether faults and alarms on this zone are reported to the monitoring station. |
| `hardwire_type` | no, default `"0"` | Wiring for zones 2 to 8, ignored for zone 1 (always end-of-line) and zones 9 and up: `"0"` end-of-line resistor, `"1"` normally closed, `"2"` normally open, `"3"` zone doubling, `"4"` double-balanced. |
| `response_time` | no, default `"1"` | Loop response for zones 1 to 8: `"0"` 10 ms, `"1"` 350 ms, `"2"` 700 ms, `"3"` 1.2 s. |
| `confirm` | yes | Must be `true`. This always opens Program Mode. |
| `confirm_life_safety` | no, default `false` | Must be `true` when `zone_type` is 9, 14 or 16. Getting a smoke or CO detector's zone wrong silences it. |
| `confirm_unverified_model` | no, default `false` | Must be `true` for any panel model not verified against its own programming guide. Verify the result at the keypad. |

### `envisalink_field_programmer.set_system_timing`

Guided edit of a single timing data field. Always opens Program Mode, so an
installer code must be configured and `confirm` must be true. Available on
the residential VISTA models (system-wide fields) and the commercial
VISTA-128BP/250BP (partition-specific fields, provisional).

| Field | Required | Description |
|---|---|---|
| `entry_id` | yes | Config entry to program. |
| `field` | yes | Timing field id for this panel. Residential VISTA: `34` exit delay, `35` entry delay 1, `36` entry delay 2, `84` auto-stay arm. Commercial VISTA: `09` to `12`, entry/exit delay 1 and 2. An id the selected model does not have is refused. |
| `value` | yes | Residential exit and entry delays: seconds, 0 to 96, or the field's extended-time codes; auto-stay arm: 0 to 3. Commercial fields: units of 15 seconds, 0 or 2 to 15 (4 is 60 seconds). |
| `partition` | no, default `1` | Partition to program, 1 to 8. Used only by panels with partition-specific timing (commercial VISTA); ignored for residential. |
| `confirm` | yes | Must be `true`. This always opens Program Mode. |
| `confirm_unverified_model` | no, default `false` | Must be `true` for any panel model not verified against its own programming guide. |

### `envisalink_field_programmer.program_function_key`

Guided assignment of one keypad function key (the `*57` menu). Always opens
Program Mode, so an installer code must be configured and `confirm` must be
true. Residential VISTA only.

| Field | Required | Description |
|---|---|---|
| `entry_id` | yes | Config entry to program. |
| `key` | yes | Which function key: `A`, `B`, `C` or `D`. |
| `partition` | yes | Partition the key acts on, 1 to 3. |
| `action` | yes | `0` default emergency, `1` single-button paging, `2` display time, `3` arm away, `4` arm stay, `5` arm night-stay, `6` step arming, `7` output device command, `8` communication test. |
| `confirm` | yes | Must be `true`. This always opens Program Mode. |
| `confirm_unverified_model` | no, default `false` | Must be `true` for any panel model not verified against its own programming guide. |

## Examples

Entity ids below assume an entry titled "Envisalink Field Programmer
(192.168.1.50)"; yours follow your Envisalink's address.

Bypass the garage zone every night at 22:00 and lift the bypass in the
morning, using the switch entity (enable it in the entity registry first):

```yaml
automation:
  - alias: Bypass the garage door overnight
    triggers:
      - trigger: time
        at: "22:00:00"
    actions:
      - action: switch.turn_on
        target:
          entity_id: switch.envisalink_field_programmer_192_168_1_50_zone_5_bypass
  - alias: Lift the garage bypass in the morning
    triggers:
      - trigger: time
        at: "06:30:00"
    actions:
      - action: switch.turn_off
        target:
          entity_id: switch.envisalink_field_programmer_192_168_1_50_zone_5_bypass
```

Tell someone when the Envisalink drops off the network (every entity goes
unavailable together, so watching one is enough):

```yaml
automation:
  - alias: Envisalink connection lost
    triggers:
      - trigger: state
        entity_id: alarm_control_panel.envisalink_field_programmer_192_168_1_50_partition
        to: unavailable
        for: "00:05:00"
    actions:
      - action: notify.notify
        data:
          message: The Envisalink has been unreachable for five minutes.
```

A script that sets the exit delay to 60 seconds. It opens Program Mode, so
run it only when nobody is relying on the panel for the next few seconds,
and check the result at the keypad afterwards (`installer code` + `#` + `56`
is the review-only menu; timing fields are read back with `*34` inside
Program Mode):

```yaml
script:
  set_exit_delay_to_one_minute:
    alias: Set the exit delay to 60 seconds
    sequence:
      - action: envisalink_field_programmer.set_system_timing
        data:
          entry_id: "{{ state_attr('alarm_control_panel.envisalink_field_programmer_192_168_1_50_partition', 'config_entry_id') }}"
          field: "34"
          value: 60
          confirm: true
```

Retype zone 6 as an interior follower, reporting on, standard wiring:

```yaml
action: envisalink_field_programmer.program_zone
data:
  entry_id: "{{ state_attr('alarm_control_panel.envisalink_field_programmer_192_168_1_50_partition', 'config_entry_id') }}"
  zone_number: 6
  zone_type: 4
  partition: 1
  report_enabled: true
  confirm: true
```

## The Lovelace card

Registered on setup. Add it to a dashboard:

```yaml
type: custom:envisalink-field-programmer-card
title: Home Alarm
alarm_entity: alarm_control_panel.envisalink_field_programmer_192_168_1_50_partition
```

Zones and the system-trouble sensor are auto-detected from the same config
entry as `alarm_entity` (matched via the `config_entry_id` attribute each
entity carries). Pass `zone_entities: [...]` explicitly if you would rather
list them yourself, or `show_programming_console: false` to hide the
field-programming panel entirely.

The field-programming panel (collapsed behind a "Field Programming" button)
has four tabs: **Zones**, **Timing**, **Function Keys** (the guided forms),
and **Raw** (the keystroke escape hatch). Colors are loosely inspired by
Envisalink/EyezOn's own site palette (a crimson/violet/amber accent trio) for
visual harmony with the hardware this talks to, not a reproduction of their
branding, and it respects Home Assistant's light and dark theme for borders,
surfaces and text.

Card source lives in `www/envisalink-field-programmer-card/` (TypeScript +
Lit, built with esbuild). The build output is committed to
`custom_components/envisalink_field_programmer/www/envisalink-field-programmer-card.js`;
that is the file HACS and Home Assistant ship and serve. The repo-root
`www/envisalink-field-programmer-card/` is a dev workspace only, not something
HACS installs. If you change the card:

```bash
cd www/envisalink-field-programmer-card
npm install
npm run build
```

## Known limitations

- **One TPI client.** The Envisalink serves one client at a time; see above.
- **No read-back.** Nothing about the panel's programming can be read over
  TPI, so every field-programming action is blind and must be checked at the
  keypad.
- **No entry-delay ("pending") state.** Exit delay is detected from the
  keypad's display text; entry delay is not represented, matching the
  reference `pyenvisalink` implementation.
- **Zone state lags up to 30 seconds** (the zone timer dump cadence);
  partition state is immediate.
- **Bypass state is optimistic.** The panel does not say which zone was
  bypassed, so the switch assumes success and clears with the partition's
  bypass flag.
- **Guided programming is refused on the DSC models and for zones on the
  commercial VISTA models**; arm, disarm and bypass still work there.
- **The panel has no identity over TPI.** No serial, no MAC, so an entry is
  identified by its address. A module's MAC is known only if a DHCP discovery
  supplied it, and that is what lets a move be followed automatically.

## Troubleshooting

Hit "Could not connect", a config entry that fails to set up, a request to
re-authenticate, an action refused as "not loaded", the card editor saying
"Custom element doesn't exist", or a card that looks like a plain default
tile instead of the custom design? See
**[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**. It covers the real issues hit
setting this up: connection errors including the single-TPI-client limit, a
Home Assistant update breaking compatibility, browser-cache issues with the
Lovelace card, and what to check when field programming does not seem to have
done anything.

Check Settings, System, Repairs too: a session that has been down for a few
minutes puts the reason there rather than leaving it in the log.

## What's verified vs. what needs your hardware

**Protocol correction (2026-07-04):** this integration still talks **TPI**,
the same Envisalink protocol on the same port 4025 it always has. What was
wrong was not the protocol's name or which system it connects to; it was this
integration's understanding of TPI's **wire-level framing**. An earlier
version was built from the "EnvisaLink TPI Programmer's Document v1.08" PDF
(checksum framing, 3-digit numeric command codes), which describes a real but
different variant of TPI than what a real EVL-4 + VISTA-21iP speaks. This was
caught during real-hardware testing (a `checksum mismatch for 'Login:'` error
in the core logs) and confirmed by reading raw socket traffic and the
actively maintained `pyenvisalink` library (used by the confirmed-working
`envisalink_new` integration). The whole client/state-machine layer was
rewritten against the real protocol: a plain-text `Login:`/`OK`/`FAILED`
handshake, then `%CODE,DATA$` / `^CODE,DATA$` framing with **no checksum**,
one-keystroke-per-frame transmission, and arm/disarm done by typing the user
code plus a mode digit (exactly like a physical keypad) rather than a
dedicated command. See `client.py`'s and `state_machine.py`'s module
docstrings, and DEVELOPMENT.md, for the full details. The Vista `*56`/`*57`
field-programming *keystroke* language itself (as opposed to how those
keystrokes get sent over the wire) was unaffected by this correction.

What the automated test suite exercises (`pytest tests/`; the count is in
the CI run, not here, because it goes stale):

- **TPI wire protocol**: sentinel stripping, frame parsing and per-event field
  tokenizing (`%00` keypad updates, `%03` realtime CID events, `%FF` zone
  timer dumps) against hand-built frames matching the real format.
- **Login handshake, keepalive, disconnect and reconnect, one-keystroke-per-
  frame transmission**, against a real asyncio TCP server standing in for the
  Envisalink (`tests/helpers.py::FakeEnvisalinkServer`, itself implementing
  the real protocol), not a mocked transport.
- **State machine**: icon-LED flag decoding into partition state (ready,
  armed mode, alarm, trouble, AC/battery), zone open/closed detection from
  the periodic zone timer dump, and CID-event-based installer-mode and
  last-armed/disarmed-user tracking.
- **Keystroke safety guard**: every branch (valid characters, Program Mode
  detection with and without a known installer code, confirmation override).
- **Field-programming keystroke translation**: every builder function (zone
  programming across the zone-1 / zone-2-8 / zone-9+ prompt variations,
  system timing including the special extended-delay codes, function keys)
  checked against exact expected keystroke strings, both as pure unit tests
  and end to end against the fake TPI server.
- **Config flow with recovery from every error, reauth, options, entity
  creation, setup failure handling, disconnect and reconnect, action
  refusals, diagnostics redaction, and all three field-programming actions'
  confirm / confirm_life_safety / installer-code gates**: against the real
  Home Assistant config-entry machinery via
  `pytest-homeassistant-custom-component`, still driven by the fake TPI
  server.

**Confirmed against real hardware (2026-07-04):** the config flow's login
handshake (once corrected to the real protocol), error handling, and HACS
installation and setup work end to end against a live Envisalink EVL-4 +
VISTA-21iP. Also confirmed: the Envisalink's TPI server only accepts one
client connection at a time.

**What still needs your real Envisalink and panel to confirm:**

- Arm/disarm via keystrokes (user code + mode digit) end to end against a
  live partition; the wire mechanism is confirmed correct against the real
  protocol but has not been exercised against a real panel while armed.
- Whether your Vista panel accepts the zone-bypass keystroke sequence
  (`*1zz#`) exactly as documented; this is standard Vista/Ademco keypad
  behaviour but has not been confirmed against your specific panel revision.
- Zone open/closed detection via the periodic zone timer dump (`%FF`); the
  decode logic matches the reference `pyenvisalink` implementation exactly
  but has not been cross-checked against a real open or closed zone.
- Exit-delay detection, which relies on a substring check ("You may exit
  now" / "May Exit Now") against the keypad's free-text display; this
  integration deliberately does not attempt fuller alpha-text parsing (see
  `state_machine.py`), so entry-delay ("pending") state is not represented
  at all, matching a known limitation in the reference implementation too.
- **The entire field-programming keystroke sequences** (`*56` zone
  programming prompt order, `*57` function key A/B/C/D-to-digit mapping,
  numbered data field entry): built strictly from the programming guide's
  documented prompt flow, never confirmed against a live panel. The A/B/C/D
  key digit mapping in particular (`field_programming.py::_FUNCTION_KEY_DIGIT`)
  is flagged in code as the first thing to check if `program_function_key`
  does not do what is expected. **Test any field-programming change on a
  non-critical zone first, and verify the result at the physical keypad**
  (installer code + `#` + `56`, the review-only mode) before trusting it on a
  real fire or security zone.

## Panel model support

You pick your panel model in the config flow. Support is delivered through a
**dialect** layer (`custom_components/envisalink_field_programmer/panels/`)
that separates the panel-agnostic guided UI from the family-specific
keystroke grammar and zone-type data.

Because sending the *wrong* keystrokes to a real fire/security panel can
silence a smoke detector or lock the panel up, and the TPI protocol gives no
read-back to catch it, every model carries an honest **verification level**,
and guided programming against anything less than fully verified requires an
explicit `confirm_unverified_model: true` acknowledgment on top of the normal
confirmations.

| Model | Family | Verification | Notes |
|---|---|---|---|
| **VISTA-21iP** | Honeywell VISTA | Verified | Built from its own programming guide (K14488PRV3) and partially hardware-tested. The reference implementation. |
| **VISTA-20P / 15P** | Honeywell VISTA | Verified | Cross-checked field by field against the VISTA-15P/20P Programming Guide (2026-07-05): program-mode entry, `*56`/`*57` menus, `*34`/`*35`/`*36`/`*84` timing, and the whole zone-type table are identical to the 21iP. |
| **VISTA-10P** | Honeywell VISTA | Verified | Cross-checked against the VISTA-10P Programming Guide. Same grammar and zone types; zones 1-6 hardwired + 9-24 RF (no zones 7-8), single partition. |
| VISTA-128BP / 250BP | Honeywell VISTA | Provisional, timing only | Commercial panels (K5894PRV6): `<code>8000` entry, partition-specific `*09`-`*12` timing, `#93` zone menu. Guided **timing** is supported (its own dialect); guided **zone** programming is refused, since the `#93` flow is too conditional to drive without hardware. Timing is guide-derived, not hardware-confirmed, so it stays Provisional (needs `confirm_unverified_model`). Arm/disarm/bypass work. |
| DSC PC1555 / 1555MX / 1575 / 5010 / 5020 / 1616 / 1832 / 1864 | DSC PowerSeries | Provisional, guided disabled | Section-based (`*8` + code) grammar and zone-definition reference checked against real DSC manuals (PC1616/1832/1864 v4.6, PC1555MX, PC5020); the installer-mode guard works. Section keystroke *builders* (`build_dsc_zone_definitions`, `build_dsc_partition_timing`) exist and are unit-tested, but nothing is wired to send them: the transport still speaks Honeywell TPI, so guided DSC programming needs a DSC transport (and hardware verification) before it can be enabled. |

The four **Verified** residential VISTA panels are fully field-programmable.
The commercial VISTA panels add guided **timing** (Provisional; verify at the
keypad); their `#93` zone flow and the DSC panels remain selectable and safe
(the DSC keystroke builders exist and are tested, but unwired). What is left
is genuinely hardware-gated: a conditional commercial `#93` zone builder, and
a DSC transport layer. Both need a real panel to trust. Contributions welcome.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full dev environment setup,
including some non-obvious Windows/asyncio test-harness gotchas. Quick start:

```bash
python -m venv .venv
source .venv/Scripts/activate  # or .venv/bin/activate on Linux/Mac
pip install pytest-homeassistant-custom-component pytest-cov ruff mypy
python -m pytest tests -q          # pure suite plus tests/ha when the harness is installed
ruff check . && ruff format --check .
python -m mypy custom_components/envisalink_field_programmer
python tools/validate_local.py
```

`.github/workflows/tests.yml` runs the same steps on every push with Home
Assistant installed (that run is the one that counts for `mypy --strict` and
the `tests/ha` suite); `.github/workflows/ci.yml` runs the official
`hassfest` and HACS validation actions and rebuilds and diffs the Lovelace
card. `custom_components/envisalink_field_programmer/quality_scale.yaml`
records where the integration stands against Home Assistant's Integration
Quality Scale, rule by rule, with a reason on every rule not yet met.

## License

MIT; see [LICENSE](LICENSE).
