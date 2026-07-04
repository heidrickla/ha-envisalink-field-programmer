# Troubleshooting

Real issues hit while setting this integration up, in the order you're
likely to hit them: connecting, then the card, then field programming. If
none of these match what you're seeing, check
[Settings → System → Logs](https://my.home-assistant.io/redirect/logs/) (or
`ha core logs` over SSH) for the actual traceback and open an issue with it
— see the [Backups](README.md#backups-what-this-can-and-cant-capture)
section's diagnostics download for a full state snapshot to attach too.

## Setup / config flow

### "Could not connect to the Envisalink at that host/port"

Two different causes produce this exact same message:

1. **Wrong host/IP or port.** Default TPI port is 4025. Confirm the
   Envisalink's IP hasn't changed (check your router's DHCP leases if it's
   not a static/reserved address).
2. **Another integration or app already holds the TPI connection.** The
   Envisalink's TPI server only accepts **one client connection at a
   time** — this is a hardware/firmware limit, not a bug. If
   `envisalink_new` (or anything else that talks TPI to this device) is
   already set up and enabled, this integration cannot connect until you
   disable that other entry. See the
   [Installation](README.md#the-envisalink-only-accepts-one-tpi-client-at-a-time)
   section for the full explanation. **Diagnostic shortcut**: Settings →
   Devices & Services → find any other Envisalink integration → confirm
   whether it's enabled. If it is, that's almost certainly the actual
   cause, no matter how many times you double-check the password.

### "The Envisalink rejected that password"

This is the plain-text password from the Envisalink's own local web page
login (Settings tab), not your Vista user code or installer code — those
are separate fields in this integration's setup form. If you're sure it's
right, check whether it was recently changed from the device's local web
UI (`http://<envisalink-ip>`), and confirm there's no leading/trailing
whitespace if you copy-pasted it.

**Finding the password if you don't remember it**: it's whatever you use
to log into the Envisalink's own local web page. If you've genuinely lost
it and never changed it from the factory default, check the sticker on
the device itself or the manual — EyezOn's default is commonly `user`,
but don't assume that without checking, since a previous
owner/installer may have changed it.

**Confirming what Home Assistant currently has saved for another
integration** (e.g. to compare against a working `envisalink_new` setup):
it's in `/config/.storage/core.config_entries`, under that integration's
entry, `data.password`. **Treat this file like a secrets file** — it holds
plain-text credentials for *every* integration configured on this Home
Assistant instance, not just this one. Never paste its contents anywhere,
including into a chat with an AI assistant; read only the one field you
need.

**The gotcha that cost real debugging time during this integration's own
initial setup**: pulling the password directly from that file and
confirming it was byte-for-byte correct, but the connection *still*
failed. If that happens to you, don't keep re-checking the password —
look at the other two causes on this page first (single-TPI-client limit,
or check the log for a real traceback rather than just the generic
"rejected" message). In this integration's case specifically, the
password was correct the entire time; the actual bug was that the client
was speaking the wrong wire protocol entirely, unrelated to credentials
at all — see the "Protocol correction" note in
[README.md](README.md#whats-verified-vs-what-needs-your-hardware) if
you're curious how deep that rabbit hole went.

### Integration shows "Failed to set up" after installing or after a Home Assistant update

Check the log for an `ImportError` or `AttributeError` naming something
from `homeassistant.const` or `homeassistant.components.*` — Home
Assistant periodically renames or removes constants/enums between
releases (this happened once already: `STATE_ALARM_ARMING` and friends
were removed from `homeassistant.const` in favor of an
`AlarmControlPanelState` enum). If you see this, it means a Home Assistant
update broke compatibility with whatever version of this integration you
have installed — check for a newer release, or
[open an issue](https://github.com/heidrickla/ha-envisalink-field-programmer/issues)
with the exact traceback and your Home Assistant version.

## The Lovelace card

### The card editor says "Custom element doesn't exist: envisalink-field-programmer-card"

This looks like a broken install, but in practice it's almost always a
**stale cached copy of the Home Assistant frontend** in your browser —
Home Assistant's frontend is a PWA with its own service-worker cache, so a
normal reload (even a hard refresh) doesn't always pick up a newly
registered card resource.

**Fastest way to confirm**: open your Home Assistant dashboard in a fresh
Incognito/Private window (or on another device you haven't loaded it on
recently, e.g. your phone). If the card works there, it's confirmed to be
a stale-cache issue on your original browser, not a real problem — this is
exactly what happened during this integration's own initial setup.

**Fix for the affected browser**, either:
- DevTools (F12) → **Application** tab → **Service Workers** →
  **Unregister**, then reload, or
- DevTools → **Application** tab → **Storage** → **Clear site data**, then
  reload and log back in.

If it's still broken in a fresh incognito window too, that's a real
problem — check that `custom_components/envisalink_field_programmer/www/envisalink-field-programmer-card.js`
actually exists (Settings → Devices & Services → this integration →
confirm it installed fully), and check the browser console (F12 →
Console) for an actual script error rather than just the "doesn't exist"
message.

### I added a card but it looks like a plain default tile, not the custom design

The card picker's search sometimes surfaces the entity itself (a default
Home Assistant Tile/entity card) rather than the custom card when you
search by name. The real custom card looks visually distinct — dark theme
with crimson/violet/amber accents, its own zone-list layout, and a
"Field Programming" button built in, not a generic entity tile.

Fix: edit the card → delete it → **"+ Add Card"** → scroll to the very
bottom of the list to **"Manual"** (don't search by name) → paste:

```yaml
type: custom:envisalink-field-programmer-card
title: Home Alarm
alarm_entity: alarm_control_panel.<your_partition_entity>
```

### Card configuration YAML gets corrupted while typing/pasting (e.g. `typetype:` or a stray `: ""` after an entity ID)

The dashboard's YAML editor can auto-complete mid-paste in a way that
duplicates or appends text. Select all the text in the editor (click
inside it, Ctrl+A, Delete) and paste the config fresh; if it corrupts
again, paste one line at a time and press `Escape` to dismiss any
autocomplete dropdown before moving to the next line.

### I don't know what to put for `alarm_entity` in the card config

It's the `alarm_control_panel` entity this integration created, named
after your Envisalink's host/IP — go to **Settings → Devices & Services →
Envisalink Field Programmer → Entities** and copy the entity ID for the
"Partition" entity (or "Partition N" if you have more than one), e.g.
`alarm_control_panel.envisalink_field_programmer_10_10_52_6_partition`.
Developer Tools → States is another way to browse and confirm it, and
lets you check the entity actually has a real state (not `unavailable`)
before you wire up the card.

### The card doesn't show my zones, or shows the wrong ones

Zones and the system-trouble sensor are auto-detected by matching a
`config_entry_id` attribute every entity from this integration carries —
so this only works if `alarm_entity` and the zone entities came from the
*same* config entry (i.e. the same Envisalink setup). If you have more
than one Envisalink configured, or the auto-detection isn't finding what
you expect, pass the zone list explicitly instead:

```yaml
type: custom:envisalink-field-programmer-card
alarm_entity: alarm_control_panel.envisalink_field_programmer_10_10_52_6_partition
zone_entities:
  - binary_sensor.envisalink_field_programmer_10_10_52_6_zone_1
  - binary_sensor.envisalink_field_programmer_10_10_52_6_zone_2
```

## Field programming

### I ran `program_zone` (or another field-programming service/tab) and nothing seems to have changed

There is genuinely no read-back over this protocol — the integration
cannot confirm what the panel actually did. Before assuming it failed:

- Confirm you set an **installer code** in this integration's options
  first (Configure → Installer code) — without it, field programming is
  disabled entirely.
- Confirm you checked the "I understand this opens Program Mode"
  confirmation box (and the life-safety one too, if applicable) — the
  service call silently rejects the request otherwise (check the log for
  a `KeystrokeGuardError` or a voluptuous schema validation error).
- **Verify at the physical keypad**: installer code + `#` + `56` opens the
  review-only zone programming menu so you can walk through and confirm
  the actual current value, without changing anything. This is the only
  reliable way to confirm a field-programming change actually took.

See [Safety](README.md#safety-read-this) for the full reasoning behind
why this integration is deliberately cautious here.
