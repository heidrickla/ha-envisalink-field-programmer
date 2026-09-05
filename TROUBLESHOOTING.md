# Troubleshooting

Real issues hit while setting this integration up, in the order you're
likely to hit them: connecting, then field programming. If
none of these match what you're seeing, check
[Settings → System → Logs](https://my.home-assistant.io/redirect/logs/) (or
`ha core logs` over SSH) for the actual traceback and open an issue with it
— see the [Backups](README.md#backups-what-this-can-and-cant-capture)
section's diagnostics download for a full state snapshot to attach too.

## Setup / config flow

### "Could not connect to the Envisalink at that host/port"

Two different causes produce this exact same message — check both before
assuming your host/port/password are wrong:

1. **Wrong host/IP or port.** Default TPI port is 4025. Confirm the
   Envisalink's IP hasn't changed (check your router's DHCP leases if it's
   not a static/reserved address).
2. **The single-TPI-client-instance gotcha** (see below) — by far the more
   common cause once you've confirmed the host/port are right.

### Gotcha: the Envisalink only accepts one TPI client at a time, ever

This is the single biggest time-sink during this integration's own
real-hardware setup, so it gets called out on its own. The Envisalink's
TPI server (port 4025) is a **hardware/firmware limit, not a bug in any
integration**: it accepts exactly **one** client connection at a time,
full stop. It doesn't queue a second connection, doesn't share the feed —
it just refuses the new connection outright, which surfaces here as the
generic "Could not connect to the Envisalink at that host/port" error,
indistinguishable from a genuinely wrong host/port.

This means:

- If `envisalink_new`, this integration, the Envisalink's own mobile app,
  Total Connect, or literally anything else is already holding a TPI
  session to this device, nothing else can connect until that one
  disconnects.
- **You cannot run this integration and `envisalink_new` (or any other
  TPI-based tool) at the same time against the same Envisalink**, full
  stop — not "shouldn't", genuinely *can't*. Decide which one you want
  active day-to-day (e.g. `envisalink_new` for daily arm/disarm/status,
  this one only when you need to do field programming) and disable the
  other rather than trying to have both enabled.
- Disabling one to enable the other is a manual toggle, not automatic —
  if you disable `envisalink_new` to test this integration, remember it's
  still disabled afterward; nothing re-enables it for you.

**Diagnostic shortcut**: Settings → Devices & Services → find any other
Envisalink integration on this Home Assistant instance → confirm whether
it's enabled. If it is, that's almost certainly the actual cause of a
"cannot connect" error here, no matter how many times you re-check the
password. See
[Installation](README.md#the-envisalink-only-accepts-one-tpi-client-at-a-time)
in the README for where this was originally confirmed against real
hardware.

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
check the single-TPI-client-instance gotcha above first, and if that's
not it either, get the actual traceback from the log rather than trusting
the generic "rejected"/"cannot connect" message. In this integration's
case specifically, the password was correct the entire time; the actual
bug was that the client was speaking the wrong wire protocol entirely,
unrelated to credentials at all — see the "Protocol correction" note in
[README.md](README.md#whats-verified-vs-what-needs-your-hardware) if
you're curious how deep that rabbit hole went.

### The entry asks you to re-authenticate

The Envisalink rejected the stored password at setup, so the entry stops
retrying and opens a repair-style prompt asking for the current password.
Enter the password from the Envisalink's local web page (Settings tab);
the flow tests it before storing it and reloads the entry on success. If
the old password still works from the web page, check that nothing else
changed it, and see the single-TPI-client gotcha above, because a busy
port is reported separately as "Could not connect", never as a
rejected password.

### A repair issue says the Envisalink is not answering

Settings, System, Repairs shows "Envisalink at &lt;address&gt; is not
answering" once five reconnects in a row have failed, about two and a
half minutes. It is not a separate fault: it is the integration naming
the likeliest cause of a silence it cannot see past, which is another
client holding the single TPI session (see the gotcha above). Disconnect
that client, or power-cycle the Envisalink, and the issue clears itself
when the session comes back. Deleting the entry removes it too.

If nothing else is connected, the module has probably lost power or its
network link, or its address has changed. If the address changed and Home
Assistant has seen a DHCP lease from the module, the entry follows on its
own; otherwise reconfigure the entry (three-dot menu on the entry,
Reconfigure) and type the new address. The entry keeps its entities and
their history either way.

### An action is refused with "is not loaded" or "No Envisalink Field Programmer entry has the id"

The actions are registered as soon as the integration loads, whether or
not an entry is connected, so a call while the entry is failing to set
up, is disabled, or is mid-reload is refused with a message naming the
entry rather than sent nowhere. Fix the entry first (Settings, Devices &
services). The id message means the `entry_id` in the call matches no
entry of this integration; use the config entry picker in the UI, or read
the `config_entry_id` attribute off any of the integration's entities.

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

## The device page

### Where the programming fields are

**Settings → Devices & services → Envisalink Field Programmer**, then the
device. The fields are in the **Configuration** section and **Last
programming result** is under **Diagnostic**. There is no card to add and
no dashboard resource to register.

### The card from 0.3.x is gone

0.4.0 removed the bundled `envisalink-field-programmer-card` and everything
that served it. A card you placed on a dashboard shows as a missing custom
element until you delete it; delete it and use the device page instead.
Nothing else is left behind — the resource was registered at runtime, never
written into your dashboard resources.

### I don't see any programming fields at all

The device page only offers the operations the selected panel model's
dialect actually drives. A **DSC** entry gets none of them, and a
**commercial VISTA** (128BP/250BP) gets the timing form only. That is
deliberate: buttons that always refuse are worse than no buttons. Arm,
disarm and bypass work on all of them. See
[Panel model support](README.md#panel-model-support).

### A button says it needs the Confirm programming switch on

That is the safety gate, not a bug. Turn on **Confirm programming**, then
press the button. It turns itself off again after every attempt, so if
you press twice you have to turn it on twice — one confirmation
authorizes one write.

### A button says to set a field first

The operation needs a value that is still unset (the message names which
one). Set it and press again. Nothing was sent to the panel.

### Last programming result says "Refused before sending"

A guard said no and the panel heard nothing. The `detail` attribute of the
sensor carries the exact reason. The usual ones: no installer code in the
options, a life-safety zone type without **Confirm life-safety zone type**,
an unverified panel model without **Confirm unverified panel model**, or a
timing value the chosen field cannot take.

### Last programming result says "Failed while sending"

The sequence was sent and the module rejected it or the session dropped
part-way, so **what reached the panel is unknown**. Check the log and the
`detail` attribute, then verify at the keypad before pressing anything
again.

## Field programming

### I programmed something and nothing seems to have changed

There is genuinely no read-back over this protocol — the integration
cannot confirm what the panel actually did. Before assuming it failed:

- Confirm you set an **installer code** in this integration's options
  first (Configure → Installer code) — without it, field programming is
  disabled entirely.
- Check **Last programming result** on the device. `Accepted` means the
  Envisalink acknowledged every keystroke; anything else names the reason
  in its `detail` attribute. If you used the action rather than the
  buttons, the refusal is in the response to the call and in the log.
- **Verify at the physical keypad**: installer code + `#` + `56` opens the
  review-only zone programming menu so you can walk through and confirm
  the actual current value, without changing anything. This is the only
  reliable way to confirm a field-programming change actually took.

See [Safety](README.md#safety-read-this) for the full reasoning behind
why this integration is deliberately cautious here.
