# Envisalink Field Programmer

A standalone Home Assistant custom integration for a Honeywell/Ademco **VISTA**
alarm panel, bridged locally over an **EyezOn Envisalink** (EVL-3/EVL-4)
module. No cloud, no Total Connect — just your panel's keybus, your LAN, and
Home Assistant.

Envisalink Field Programmer talks the Envisalink **TPI** (Third Party Interface) protocol
directly over TCP (port 4025) with its own asyncio client — it does not
depend on `pyenvisalink` or any other integration.

## Why this exists (and how it relates to `envisalink_new`)

[`ufodone/envisalink_new`](https://github.com/ufodone/envisalink_new) is a
mature, actively maintained HACS integration that already covers arm/disarm,
zone/partition status, and bypass switches for both DSC and Honeywell panels
well. If all you want is basic alarm control, use that one.

This integration's actual reason to exist is **guided installer field
programming** — a structured, plain-language layer over Vista's `*56`/`*57`
keypad programming language (zone types, entry/exit timing, function keys),
with strong confirmation gates given the fire/UL-safety stakes of getting
installer programming wrong. Nothing else exposes this through Home
Assistant today. Arm/disarm/status/zone entities and a polished Lovelace
console card come along for the ride, but the programming layer is the
point.

## Features

- Config flow setup (host/port/password/panel model/user code/zone & partition
  counts); an optional installer code (set later, in the integration's options)
  turns on field programming. Panel model defaults to the VISTA-21iP — see
  [Panel model support](#panel-model-support) for the full model list and what
  each one's support level actually means
- One `alarm_control_panel` entity per partition: arm away/home/night, disarm
- One `binary_sensor` per zone (open/closed), plus per-zone `switch` entities
  for bypass (disabled by default in the entity registry — enable the ones
  you want)
- A system trouble `binary_sensor` (AC power / low battery / general trouble
  per partition, plus installer-mode)
- Diagnostic sensors (last raw panel event, last user to arm/disarm each partition)
- **Guided field-programming services** — `program_zone`, `set_system_timing`,
  `program_function_key` — plus the lower-level `send_keystrokes` and
  `toggle_zone_bypass` (see [Field programming](#field-programming) and
  [Safety](#safety-read-this))
- Built-in diagnostics download (Settings → Devices → Envisalink Field Programmer →
  Download Diagnostics) — see [Backups](#backups-what-this-can-and-cant-capture)
- A custom `envisalink-field-programmer-card` Lovelace card, auto-registered on setup —
  no manual "add resource" step, with guided Zone/Timing/Function-Key tabs
  plus a raw-keystroke escape hatch

## Installation

**HACS (custom repository):** add this repo as a custom repository (category:
Integration), then install "Envisalink Field Programmer".

**Manual:** copy `custom_components/envisalink_field_programmer/` into your Home
Assistant `config/custom_components/` directory and restart.

Then: Settings → Devices & Services → Add Integration → "Envisalink Field Programmer".

You'll need:
- The Envisalink's IP address and TPI port (4025 by default)
- The Envisalink's password (same one used for its local web page)
- Optionally, a default user code for disarming from Home Assistant
- Optionally (in the integration's options, after setup), your **installer
  code** — only needed if you want to use field programming

### The Envisalink only accepts one TPI client at a time

Confirmed against real hardware: if `envisalink_new` (or any other
integration/app already talking TPI to this Envisalink) is connected,
setting up this integration against the same device will fail with
"Could not connect to the Envisalink at that host/port" — not because the
host/port/password are wrong, but because the Envisalink's TPI server
(port 4025) refuses a second simultaneous connection outright. This is a
hardware/firmware limit, not a bug in either integration.

If you hit that error and you're sure your connection details are correct,
check whether another integration already holds the connection
(Settings → Devices & Services → find it → confirm it's enabled) and
disable it first. The two integrations can't both be connected at the same
time, so plan your setup around whichever one you want active day-to-day
(e.g. keep `envisalink_new` enabled for daily zone/arm status, and only
temporarily disable it and enable this one when you actually need to do
field programming, or vice versa).

## Field programming

Three guided services, each translating validated, structured input into
the exact keystroke sequence Vista expects (see
`custom_components/envisalink_field_programmer/field_programming.py`, built from the
ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3):

- **`envisalink_field_programmer.program_zone`** — zone type (translated to plain-language
  options like "Perimeter (instant)" or "Fire (smoke/heat detector)", not
  raw Vista field numbers), partition, reporting, and wiring settings for
  one zone.
- **`envisalink_field_programmer.set_system_timing`** — exit delay, entry delay 1/2, and
  auto-stay-arm.
- **`envisalink_field_programmer.program_function_key`** — assign the keypad's A/B/C/D
  function keys.

This is deliberately a **curated subset**, not the full installer field set
— output/relay programming (`*79`/`*80`/`*81`), alpha descriptors (`*82`),
and the installer-only configurable zone types (90/91) are out of scope for
now. A smaller, clearly-explained set of settings beats a full field dump
nobody can safely reason about. The guided Lovelace card tabs (Zones /
Timing / Function Keys) are the intended way to use this; the services exist
so the same logic is scriptable.

**Every one of these always opens the panel's installer Program Mode**
(typing the installer code followed by `800`), which is why they require an
installer code configured and a `confirm: true` field — see
[Safety](#safety-read-this).

## Safety (read this)

Opening Vista's installer Program Mode gives access to every data field on
the panel, including fire-zone and UL-listing-relevant settings, and once
inside, most functions (including disarm) are unavailable until you exit —
badly, that can mean a physical power cycle. Two important specifics:

- **Program Mode opens via `<installer code>800`** (e.g. `4112800` with the
  factory-default code) — not a DSC-style `*8` sequence. An earlier version
  of this integration's guard blocked `*8`, based on a generic warning in
  the Envisalink TPI spec that turns out to describe DSC panels, not Vista;
  there is no `*8` menu on a real Vista panel at all. This was corrected
  once the actual Vista programming guide was checked directly — see
  `programming.py`'s module docstring for the full explanation.
- **The TPI protocol cannot read back what's on the keypad display.** Every
  field-programming action here is genuinely "blind": if a keystroke
  sequence has a bug, or the panel is in an unexpected state, there is no
  channel to detect it before it's too late. The guided services show you
  the field values you're setting *before* sending (via the Lovelace card's
  form), but cannot show you what the panel is actually doing in response.

Given that, this integration:

- Routes **every** keystroke send — raw or guided — through a single guard
  (`custom_components/envisalink_field_programmer/programming.py`) that refuses any
  sequence matching the Program Mode trigger unless explicitly confirmed.
- Requires the three guided services' `confirm: true` field on every call
  (they always open Program Mode by design), plus an additional
  `confirm_life_safety: true` on `program_zone` whenever the target zone
  type is fire or CO — because this integration cannot verify what a zone's
  *current* type is before overwriting it.
- Never exposes raw keystrokes from the Lovelace card's normal UI — the
  guided tabs are the default; a separate "Raw" tab exists for anything they
  don't cover, gated by its own confirmation checkbox.
- Treats zone bypass (`toggle_zone_bypass`, `*1zz#`) as the one keystroke
  sequence that's always allowed without confirmation, because it's an
  ordinary end-user keypad function that never opens Program Mode.

If you don't need field programming, ignore it entirely and don't configure
an installer code — arm, disarm, status, and zone bypass never touch any of
this.

## Backups: what this can and can't capture

Home Assistant's standard **Download Diagnostics** button (on this
integration's entry) captures a timestamped JSON snapshot of everything
Home Assistant currently knows: partition/zone/system state, armed mode,
open/bypassed zones, trouble flags, last user. Grab one before you
experiment with field programming.

**What it cannot capture: the panel's actual installer field programming**
(zone types, entry/exit delays, alpha descriptors, output/relay
assignments, communicator settings, etc.). The real TPI protocol has no
command that reads that data back — it only exposes live status events
(icon-LED keypad state, realtime CID events, the zone timer dump), never the
underlying `*56`/`*58`/`*79`/`*80`/`*82`-style configuration fields. To
actually back up your panel's programming, you need to either:

- Walk each installer menu field at the keypad and record it by hand, or
- Use a Honeywell-side tool (Compass Downloader, Total Connect installer
  access) if you have access to one.

Be skeptical of any tool that claims to "read back" Vista programming over
a keypad-emulation link like this one — as far as the TPI protocol is
concerned, that data doesn't come back over the wire.

## Services

### `envisalink_field_programmer.program_zone`, `set_system_timing`, `program_function_key`

See [Field programming](#field-programming) above and `services.yaml` for
full field references — each has several fields and is best driven from the
Lovelace card's guided tabs rather than hand-written service calls.

### `envisalink_field_programmer.toggle_zone_bypass`
| field | required | description |
|---|---|---|
| `entry_id` | yes | Config entry that owns the zone |
| `zone` | yes | Zone number (1-64) |

### `envisalink_field_programmer.send_keystrokes`
| field | required | description |
|---|---|---|
| `entry_id` | yes | Config entry to send to |
| `partition` | yes | Partition number (1-8) |
| `keys` | yes | Keystrokes: digits, `*`, `#` only |
| `confirm_installer_risk` | no (default `false`) | Must be `true` to send a sequence that opens Program Mode |

## The Lovelace card

Auto-registered after setup. Add it to a dashboard:

```yaml
type: custom:envisalink-field-programmer-card
title: Home Alarm
alarm_entity: alarm_control_panel.envisalink_field_programmer_192_168_1_50_partition
```

Zones and the system-trouble sensor are auto-detected from the same config
entry as `alarm_entity` (matched via a `config_entry_id` attribute each
entity carries). Pass `zone_entities: [...]` explicitly if you'd rather
list them yourself, or `show_programming_console: false` to hide the
field-programming panel entirely.

The field-programming panel (collapsed behind a "Field Programming" button)
has four tabs: **Zones**, **Timing**, **Function Keys** (the guided forms),
and **Raw** (the original keystroke escape hatch). Colors are loosely
inspired by Envisalink/EyezOn's own site palette (a crimson/violet/amber
accent trio) for visual harmony with the hardware this talks to — not a
reproduction of their branding, and it still respects Home Assistant's
light/dark theme for borders, surfaces, and text.

Card source lives in `www/envisalink-field-programmer-card/` (TypeScript + Lit, built
with esbuild). The build output is committed to
`custom_components/envisalink_field_programmer/www/envisalink-field-programmer-card.js` — that's the
file HACS/HA actually ships and serves; `www/envisalink-field-programmer-card/` at the
repo root is a dev workspace only, not something HACS installs. If you
change the card:

```bash
cd www/envisalink-field-programmer-card
npm install
npm run build
```

## Troubleshooting

Hit "Could not connect", a config entry that fails to set up, the card
editor saying "Custom element doesn't exist", or a card that looks like a
plain default tile instead of the custom design? See
**[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — it covers the real issues
hit setting this up (connection errors including the single-TPI-client
limit, a Home Assistant update breaking compatibility, browser-cache
issues with the Lovelace card, and what to check when field programming
doesn't seem to have done anything).

## What's verified vs. what needs your hardware

**Protocol correction (2026-07-04):** to be clear about what did and didn't
change here — this integration still talks **TPI** (Third Party Interface),
the same Envisalink protocol on the same port 4025 it always has. What was
wrong wasn't the protocol's name or which system it connects to, it was
this integration's understanding of TPI's actual **wire-level framing**. An
earlier version was built from the "EnvisaLink TPI Programmer's Document
v1.08" PDF (checksum framing, 3-digit numeric command codes), which
describes a real but different variant of TPI than what a real EVL-4 +
VISTA-21iP actually speaks. This was caught during real-hardware testing
(a `checksum mismatch for 'Login:'` error in the HA core logs) and confirmed
by reading raw socket traffic and the actively maintained `pyenvisalink`
library (used by the confirmed-working `envisalink_new` integration). The
whole client/state-machine layer was rewritten against the real protocol:
a plain-text `Login:`/`OK`/`FAILED` handshake, then `%CODE,DATA$` /
`^CODE,DATA$` framing with **no checksum**, one-keystroke-per-frame
transmission, and arm/disarm done by typing the user code plus a mode digit
(exactly like a physical keypad) rather than a dedicated command. See
`client.py`'s and `state_machine.py`'s module docstrings, and
DEVELOPMENT.md, for the full details. The Vista `*56`/`*57` field-programming
*keystroke* language itself (as opposed to how those keystrokes get sent
over the wire) was unaffected by this correction.

What's actually exercised by the automated test suite (`pytest tests/`,
70 tests):

- **TPI wire protocol**: sentinel-stripping, frame parsing, and per-event
  field tokenizing (`%00` keypad updates, `%03` realtime CID events, `%FF`
  zone timer dumps) against hand-built frames matching the real format.
- **Login handshake, keepalive, disconnect/reconnect, one-keystroke-per-frame
  transmission** — against a real asyncio TCP server standing in for the
  Envisalink (`tests/helpers.py::FakeEnvisalinkServer`, itself implementing
  the real protocol), not a mocked transport.
- **State machine**: icon-LED flag decoding into partition state (ready,
  armed mode, alarm, trouble, AC/battery), zone open/closed detection from
  the periodic zone timer dump, and CID-event-based installer-mode and
  last-armed/disarmed-user tracking.
- **Keystroke safety guard**: every branch (valid chars, Program Mode
  detection with and without a known installer code, confirmation override).
- **Field-programming keystroke translation**: every builder function
  (zone programming across the zone-1 / zone-2-8 / zone-9+ prompt
  variations, system timing including the special extended-delay codes,
  function keys) checked against exact expected keystroke strings, both as
  pure unit tests and end-to-end against the fake TPI server.
- **Config flow, entity creation, coordinator reconnect/unavailable
  behavior, and all three field-programming services' confirm/
  confirm_life_safety/installer-code gates**: against the real Home
  Assistant config-entry machinery via `pytest-homeassistant-custom-component`,
  still driven by the fake TPI server.

**Confirmed against real hardware (2026-07-04):** the config flow's login
handshake (once corrected to the real protocol), error handling, and HACS
installation/setup all work correctly end-to-end against a live Envisalink
EVL-4 + VISTA-21iP. Also confirmed: the Envisalink's TPI server only accepts
one client connection at a time — see "The Envisalink only accepts one TPI
client at a time" above.

**What still needs your real Envisalink/panel to confirm:**
- Arm/disarm via keystrokes (user code + mode digit) end-to-end against a
  live partition — the wire mechanism is confirmed correct against the real
  protocol, but hasn't yet been exercised against a real panel while armed.
- Whether your Vista panel accepts the zone-bypass keystroke sequence
  (`*1zz#`) exactly as documented — this is standard Vista/Ademco keypad
  behavior but hasn't been confirmed against your specific panel revision.
- Zone open/closed detection via the periodic zone timer dump (`%FF`) — the
  decode logic matches the reference `pyenvisalink` implementation exactly,
  but hasn't yet been cross-checked against a real open/closed zone on this
  hardware.
- Exit-delay detection, which relies on a simple substring check
  ("You may exit now" / "May Exit Now") against the keypad's free-text
  display — this integration deliberately does not attempt fuller alpha-text
  parsing (see `state_machine.py`'s module docstring), so entry-delay
  ("pending") state is not represented at all, matching a known limitation
  in the reference implementation too.
- **The entire field-programming keystroke sequences** (`*56` zone
  programming prompt order, `*57` function key A/B/C/D-to-digit mapping,
  numbered data field entry) — built strictly from the programming guide's
  documented prompt flow, but never confirmed against a live panel. The
  A/B/C/D key digit mapping in particular
  (`field_programming.py::_FUNCTION_KEY_DIGIT`) is flagged in code as the
  first thing to check if `program_function_key` doesn't do what's expected.
  **Test any field-programming change on a non-critical zone first, and
  verify the result at the physical keypad** (installer code + `#` + `56`,
  the review-only mode) before trusting it on a real fire/security zone.

## Panel model support

You pick your panel model in the config flow. Support is delivered through a
**dialect** layer (`custom_components/envisalink_field_programmer/panels/`) that
separates the panel-agnostic guided UI from the family-specific keystroke
grammar and zone-type data.

Because sending the *wrong* keystrokes to a real fire/security panel can
silence a smoke detector or lock the panel up — and the TPI protocol gives no
read-back to catch it — every model carries an honest **verification level**,
and guided programming against anything less than fully verified requires an
explicit `confirm_unverified_model: true` acknowledgment on top of the normal
confirmations.

| Model | Family | Verification | Notes |
|---|---|---|---|
| **VISTA-21iP** | Honeywell VISTA | ✅ Verified | Built from its own programming guide (K14488PRV3) and partially hardware-tested. The reference implementation. |
| **VISTA-20P / 15P** | Honeywell VISTA | ✅ Verified | Cross-checked field-by-field against the VISTA-15P/20P Programming Guide (2026-07-05): program-mode entry, `*56`/`*57` menus, `*34`/`*35`/`*36`/`*84` timing, and the whole zone-type table are identical to the 21iP. |
| **VISTA-10P** | Honeywell VISTA | ✅ Verified | Cross-checked against the VISTA-10P Programming Guide. Same grammar/zone types; zones 1-6 hardwired + 9-24 RF (no zones 7-8), single partition. |
| VISTA-128BP / 250BP | Honeywell VISTA | ⚠ Provisional — guided **disabled** | Confirmed against K5894PRV6 that these commercial panels use a *different* language (`<code>8000` entry, `#93` zone menu, `*09`-`*12` timing). Guided programming is refused for them so the residential builder can't send wrong keystrokes; arm/disarm/bypass/model selection still work. A commercial-VISTA dialect is future work. |
| DSC PC1555 / 1555MX / 1575 / 5010 / 5020 / 1616 / 1832 / 1864 | DSC PowerSeries | ⚠ Provisional — guided **disabled** | Section-based (`*8` + code) grammar and the zone-definition reference table are checked against real DSC manuals (PC1616/1832/1864 v4.6, PC1555MX, PC5020), and the installer-mode guard works. Guided *per-zone* programming is intentionally **not** driven for DSC (its positional whole-section programming would risk overwriting a zone block blind, and the transport still speaks Honeywell TPI); model selection, the zone-type reference, and the guard are available. |

The four **Verified** residential VISTA panels are the ones you can fully
field-program. The commercial VISTA and DSC panels are selectable and safe
(guided programming is refused rather than done wrong); completing their guided
programming is future work — a commercial-VISTA `#93` dialect, and a DSC
section-programming path plus DSC transport. Contributions welcome.

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for the full dev environment setup,
including some non-obvious Windows/asyncio test-harness gotchas. Quick
start:

```bash
python -m venv .venv
source .venv/Scripts/activate  # or .venv/bin/activate on Linux/Mac
pip install pytest pytest-asyncio pytest-homeassistant-custom-component ruff
pytest tests/ -v
ruff check custom_components tests
```

CI (`.github/workflows/ci.yml`) additionally runs the official `hassfest`
and HACS validation actions, and rebuilds/diffs the Lovelace card.

## License

MIT — see [LICENSE](LICENSE).
