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

Vista Console is narrower and Vista-specific. Its reason to exist is:

1. A **guarded raw-keystroke / zone-bypass pathway** for Vista's keypad
   command language, with explicit safety rails around installer
   programming mode (see [Safety](#safety-read-this) below) — nothing else
   currently exposes this through Home Assistant.
2. A **built-in, auto-registered Lovelace card** (Lit/TypeScript) styled
   like a real alarm console rather than a stack of generic entity rows.

## Features

- Config flow setup (host/port/password/user code/zone & partition counts)
- One `alarm_control_panel` entity per partition: arm away/home/night, disarm
- One `binary_sensor` per zone (open/closed), plus per-zone `switch` entities
  for bypass (disabled by default in the entity registry — enable the ones
  you want)
- A system trouble `binary_sensor` (AC/battery/bell/FTC/fire/tamper/installer-mode)
- Diagnostic sensors (last raw panel event, last user to arm/disarm each partition)
- `vista_console.toggle_zone_bypass` and `vista_console.send_keystrokes`
  services (see [Safety](#safety-read-this))
- Built-in diagnostics download (Settings → Devices → Vista Console →
  Download Diagnostics) — see [Backups](#backups-what-this-can-and-cant-capture)
- A custom `vista-console-card` Lovelace card, auto-registered on setup —
  no manual "add resource" step

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

## Safety (read this)

The Envisalink TPI protocol has exactly one command for sending arbitrary
keypad input: `071`, "Send Keystroke String". It's the same mechanism
whether you're bypassing a zone (`*1zz#`) or entering full installer field
programming (`*8...`). The Envisalink's own protocol documentation calls
this out directly:

> Using the TPI commands 070 and 071, you can conceivably put the panel
> into installers mode (\*8). The danger here is that when in installers
> mode most of the commands are locked out so you could end up dead-locking
> yourself with the only way out of installers being to power cycle the
> panel.

Installer mode is also where Vista's fire-zone and UL-listing-relevant
settings live. This integration:

- Routes **every** raw-keystroke send through a single guard
  (`custom_components/vista_console/programming.py`) that refuses any
  sequence containing `*8` unless you explicitly pass
  `confirm_installer_risk: true` to the `vista_console.send_keystrokes`
  service.
- Never exposes raw keystrokes from the Lovelace card's normal UI — only
  from an explicitly-opened "Advanced Programming Console" panel with its
  own confirmation checkbox, calling the same guarded service.
- Treats zone bypass (`toggle_zone_bypass`) as the one keystroke sequence
  that's always allowed without confirmation, because it's an ordinary
  end-user keypad function with no installer-mode risk.

If you don't need the programming console, ignore it entirely — arm,
disarm, status, and zone bypass never touch this code path's confirmation
gate.

## Backups: what this can and can't capture

Home Assistant's standard **Download Diagnostics** button (on this
integration's entry) captures a timestamped JSON snapshot of everything
Home Assistant currently knows: partition/zone/system state, armed mode,
open/bypassed zones, trouble flags, last user. Grab one before you
experiment with anything in the programming console.

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
| `confirm_installer_risk` | no (default `false`) | Must be `true` to send a sequence containing `*8` |

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
advanced panel entirely.

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
36 tests):

- **TPI wire protocol**: checksum math, frame parsing, event field decoding
  — against the exact worked example in the EnvisaLink TPI spec.
- **Login handshake, keepalive, disconnect/reconnect, keystroke chunking**
  — against a real asyncio TCP server standing in for the Envisalink
  (`tests/helpers.py::FakeEnvisalinkServer`), not a mocked transport.
- **State machine**: every event code this integration understands, folded
  into partition/zone/system state.
- **Keystroke safety guard**: every branch (valid chars, installer-mode
  block, confirmation override).
- **Config flow, entity creation, coordinator reconnect/unavailable
  behavior**: against the real Home Assistant config-entry machinery via
  `pytest-homeassistant-custom-component`, still driven by the fake TPI
  server.

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

## Development

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
