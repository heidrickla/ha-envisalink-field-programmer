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
