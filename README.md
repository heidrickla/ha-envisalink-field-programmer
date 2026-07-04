# Vista Console

A standalone Home Assistant custom integration for a Honeywell/Ademco **VISTA**
alarm panel, bridged locally over an **EyezOn Envisalink** (EVL-3/EVL-4)
module. No cloud, no Total Connect — just your panel's keybus, your LAN, and
Home Assistant.

Vista Console talks the Envisalink **TPI** (Third Party Interface) protocol
directly over TCP (port 4025) with its own asyncio client — it does not
depend on `pyenvisalink` or any other integration.

## Why this exists (and how it relates to `envisalink_new`)

[`ufodone/envisalink_new`](https://github.com/ufodone/envisalink_new) is a
mature, actively maintained HACS integration that already covers arm/disarm,
zone/partition status, and bypass switches for both DSC and Honeywell panels
well. If all you want is basic alarm control, use that one.

Vista Console's actual reason to exist is **guided installer field
programming** — a structured, plain-language layer over Vista's `*56`/`*57`
keypad programming language (zone types, entry/exit timing, function keys),
with strong confirmation gates given the fire/UL-safety stakes of getting
installer programming wrong. Nothing else exposes this through Home
Assistant today. Arm/disarm/status/zone entities and a polished Lovelace
console card come along for the ride, but the programming layer is the
point.

## Features

- Config flow setup (host/port/password/user code/zone & partition counts);
  an optional installer code (set later, in the integration's options) turns
  on field programming
- One `alarm_control_panel` entity per partition: arm away/home/night, disarm
- One `binary_sensor` per zone (open/closed), plus per-zone `switch` entities
  for bypass (disabled by default in the entity registry — enable the ones
  you want)
- A system trouble `binary_sensor` (AC/battery/bell/FTC/fire/tamper/installer-mode)
- Diagnostic sensors (last raw panel event, last user to arm/disarm each partition)
- **Guided field-programming services** — `program_zone`, `set_system_timing`,
  `program_function_key` — plus the lower-level `send_keystrokes` and
  `toggle_zone_bypass` (see [Field programming](#field-programming) and
  [Safety](#safety-read-this))
- Built-in diagnostics download (Settings → Devices → Vista Console →
  Download Diagnostics) — see [Backups](#backups-what-this-can-and-cant-capture)
- A custom `vista-console-card` Lovelace card, auto-registered on setup —
  no manual "add resource" step, with guided Zone/Timing/Function-Key tabs
  plus a raw-keystroke escape hatch

## Installation

**HACS (custom repository):** add this repo as a custom repository (category:
Integration), then install "Vista Console".

**Manual:** copy `custom_components/vista_console/` into your Home
Assistant `config/custom_components/` directory and restart.

Then: Settings → Devices & Services → Add Integration → "Vista Console".

You'll need:
- The Envisalink's IP address and TPI port (4025 by default)
- The Envisalink's password (same one used for its local web page)
- Optionally, a default user code for disarming from Home Assistant
- Optionally (in the integration's options, after setup), your **installer
  code** — only needed if you want to use field programming

## Field programming

Three guided services, each translating validated, structured input into
the exact keystroke sequence Vista expects (see
`custom_components/vista_console/field_programming.py`, built from the
ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3):

- **`vista_console.program_zone`** — zone type (translated to plain-language
  options like "Perimeter (instant)" or "Fire (smoke/heat detector)", not
  raw Vista field numbers), partition, reporting, and wiring settings for
  one zone.
- **`vista_console.set_system_timing`** — exit delay, entry delay 1/2, and
  auto-stay-arm.
- **`vista_console.program_function_key`** — assign the keypad's A/B/C/D
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
  (`custom_components/vista_console/programming.py`) that refuses any
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
assignments, communicator settings, etc.). The TPI protocol has no command
that reads that data back — section 3 of the EnvisaLink TPI spec only
exposes live status events and keypad LED state, never the underlying
`*56`/`*58`/`*79`/`*80`/`*82`-style configuration fields. To actually back
up your panel's programming, you need to either:

- Walk each installer menu field at the keypad and record it by hand, or
- Use a Honeywell-side tool (Compass Downloader, Total Connect installer
  access) if you have access to one.

Be skeptical of any tool that claims to "read back" Vista programming over
a keypad-emulation link like this one — as far as the TPI protocol is
concerned, that data doesn't come back over the wire.

## Services

### `vista_console.program_zone`, `set_system_timing`, `program_function_key`

See [Field programming](#field-programming) above and `services.yaml` for
full field references — each has several fields and is best driven from the
Lovelace card's guided tabs rather than hand-written service calls.

### `vista_console.toggle_zone_bypass`
| field | required | description |
|---|---|---|
| `entry_id` | yes | Config entry that owns the zone |
| `zone` | yes | Zone number (1-64) |

### `vista_console.send_keystrokes`
| field | required | description |
|---|---|---|
| `entry_id` | yes | Config entry to send to |
| `partition` | yes | Partition number (1-8) |
| `keys` | yes | Keystrokes: digits, `*`, `#` only |
| `confirm_installer_risk` | no (default `false`) | Must be `true` to send a sequence that opens Program Mode |

## The Lovelace card

Auto-registered after setup. Add it to a dashboard:

```yaml
type: custom:vista-console-card
title: Home Alarm
alarm_entity: alarm_control_panel.vista_console_192_168_1_50_partition
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

Card source lives in `www/vista-console-card/` (TypeScript + Lit, built
with esbuild). The build output is committed to
`custom_components/vista_console/www/vista-console-card.js` — that's the
file HACS/HA actually ships and serves; `www/vista-console-card/` at the
repo root is a dev workspace only, not something HACS installs. If you
change the card:

```bash
cd www/vista-console-card
npm install
npm run build
```

## What's verified vs. what needs your hardware

This was built and tested without access to a live Envisalink or VISTA
panel. What's actually exercised by the automated test suite (`pytest tests/`,
62 tests):

- **TPI wire protocol**: checksum math, frame parsing, event field decoding
  — against the exact worked example in the EnvisaLink TPI spec.
- **Login handshake, keepalive, disconnect/reconnect, keystroke chunking**
  — against a real asyncio TCP server standing in for the Envisalink
  (`tests/helpers.py::FakeEnvisalinkServer`), not a mocked transport.
- **State machine**: every event code this integration understands, folded
  into partition/zone/system state.
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

**What still needs your real Envisalink/panel to confirm:**
- The exact login password/firewall behavior of your specific EVL
  firmware version (see the "Envisalink Application Firewall" note in the
  TPI spec — changing the default `user` password may be required for TPI
  access depending on your firmware).
- Whether your Vista panel accepts the zone-bypass keystroke sequence
  (`*1zz#`) exactly as documented — this is standard Vista/Ademco keypad
  behavior but hasn't been confirmed against your specific panel revision.
- Timing/arm-mode mapping for `032` (zero entry) if your installer has
  changed default arming behavior.
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

## Roadmap

Planned: broader panel support beyond the VISTA-21iP this was built
against — the rest of the Honeywell VISTA family (20P, 15P, 10P, 128P,
250P), which likely shares the same `*56`-style field-programming language
with per-model differences to verify, and DSC PowerSeries panels (1555,
1555MX, 1575, 5010/832, 5020/864, 1616, 1832, 1864), which use an entirely
different section-based programming language and would need its own
dialect layer alongside this one, not a small extension of it.

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
