# Troubleshooting

Issues hit setting this integration up, in the order they usually arrive:
connecting, then field programming. If none of these match, read
[Settings, System, Logs](https://my.home-assistant.io/redirect/logs/), or
`ha core logs` over SSH, for the traceback and open an issue with it. Attach
a diagnostics download for a full state snapshot; see
[Backups](README.md#backups-what-this-can-and-cant-capture).

## Setup / config flow

### "Could not connect to the Envisalink at that host/port"

Two causes produce this same message. Check both before assuming the host,
port or password is wrong:

1. Wrong host, address or port. The TPI port is 4025 by default. Confirm the
   Envisalink's address has not changed; check your router's DHCP leases if
   it is not reserved.
2. Another client already holds the Envisalink's one TPI session, covered in
   the next section. That is the more common cause once the host and port
   are confirmed.

### The Envisalink accepts one TPI client at a time

Port 4025 accepts exactly one client connection. It does not queue a second
connection and does not share the feed: it refuses the new connection, which
surfaces as "Could not connect to the Envisalink at that host/port",
indistinguishable from a wrong host or port. This is a limit of the module's
firmware, not of any integration. Confirmed against an EVL-4 and a
VISTA-21iP on 2026-07-04; see
[Installation](README.md#the-envisalink-only-accepts-one-tpi-client-at-a-time).

- While `envisalink_new`, this integration, the Envisalink's own mobile app,
  Total Connect or anything else holds a TPI session to the module, nothing
  else can connect until that one disconnects.
- This integration and `envisalink_new` cannot both be connected to the same
  Envisalink. Pick the one you want active day to day, for example
  `envisalink_new` for arm, disarm and status and this one for field
  programming, and disable the other.
- Disabling one to enable the other is a manual toggle. Nothing re-enables
  the one you disabled.

To check: Settings, Devices & services, find any other Envisalink
integration on this Home Assistant instance, and see whether it is enabled.
If it is, that is the likely cause of a "cannot connect" error here.

### "The Envisalink rejected that password"

This is the plain-text password from the Envisalink's own local web page
login, Settings tab. It is not your Vista user code or installer code; those
are separate fields in this integration's setup form. If it looks right,
check whether it was changed from the device's local web page
(`http://<envisalink-address>`), and check for leading or trailing
whitespace if you pasted it.

Finding the password: it is whatever logs in to the Envisalink's own local
web page. If it has never been changed from the factory default, the sticker
on the device and the manual carry it. EyezOn's default is commonly `user`;
check rather than assume, since a previous owner or installer may have
changed it.

Reading what Home Assistant has saved for another integration, to compare
against a working `envisalink_new` setup: it is in
`/config/.storage/core.config_entries`, under that integration's entry,
`data.password`. Treat that file as a secrets file. It holds plain-text
credentials for every integration configured on this Home Assistant
instance. Read the one field you need and paste its contents nowhere,
including into a chat with an AI assistant.

A password read byte-for-byte out of that file can still fail to connect.
Check the single-TPI-session cause above before re-checking the password,
and if that is not it, take the traceback from the log rather than trusting
the generic "rejected" or "cannot connect" message.

### The entry asks you to re-authenticate

The Envisalink rejected the stored password at setup, so the entry stops
retrying and opens a repair-style prompt asking for the current password.
Enter the password from the Envisalink's local web page (Settings tab);
the flow tests it before storing it and reloads the entry on success. If
the old password still works from the web page, check that nothing else
changed it, and read the single-TPI-session section above, because a busy
port is reported separately as "Could not connect" and never as a rejected
password.

### A repair issue says the Envisalink is not answering

Settings, System, Repairs shows "Envisalink at &lt;address&gt; is not
answering" once five reconnects in a row have failed, about two and a half
minutes. It is not a separate fault. It names the likeliest cause of a
silence the integration cannot see past, which is another client holding the
single TPI session, above. Disconnect that client, or power-cycle the
Envisalink, and the issue clears itself when the session comes back.
Deleting the entry removes it too.

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
from `homeassistant.const` or `homeassistant.components.*`. Home
Assistant renames or removes constants and enums between
releases. `STATE_ALARM_ARMING` and its siblings were removed from
`homeassistant.const` in favour of an `AlarmControlPanelState` enum, for
example. That means a Home Assistant update broke compatibility with the
version of this integration you have installed. Check for a newer release, or
[open an issue](https://github.com/heidrickla/ha-envisalink-field-programmer/issues)
with the exact traceback and your Home Assistant version.

## The device page

### Where the programming fields are

Settings, Devices & services, Envisalink Field Programmer, then the device.
The fields are in the Configuration section and Last programming result is
under Diagnostic. There is no card to add and no dashboard resource to
register.

### The card from 0.3.x is gone

0.4.0 removed the bundled `envisalink-field-programmer-card` and everything
that served it. A card you placed on a dashboard shows as a missing custom
element until you delete it. Delete it and use the device page instead.
Nothing else is left behind: the resource was registered at runtime and never
written into your dashboard resources.

### I don't see any programming fields at all

The device page only offers the operations the selected panel model's
dialect drives. A DSC entry gets none of them, and a commercial VISTA
(128BP/250BP) gets the timing form only, rather than buttons that always
refuse. Arm, disarm and bypass work on all of them. See
[Panel model support](README.md#panel-model-support).

### A button says it needs the Confirm programming switch on

That is the safety gate. Turn on Confirm programming, then press the button.
It turns itself off again after every attempt, so two presses need it turned
on twice. One confirmation authorizes one write.

### A button says to set a field first

The operation needs a value that is unset, and the message names which one.
Set it and press again. Nothing was sent to the panel.

### Last programming result says "Refused before sending"

A guard said no and the panel heard nothing. The `detail` attribute of the
sensor carries the exact reason. The usual ones: no installer code in the
options, a life-safety zone type without Confirm life-safety zone type,
an unverified panel model without Confirm unverified panel model, or a
timing value the chosen field cannot take.

### Last programming result says "Failed while sending"

The sequence was sent and the module rejected it, or the session dropped
part-way, so what reached the panel is unknown. Check the log and the
`detail` attribute, then verify at the keypad before pressing anything
again.

## Field programming

### I programmed something and nothing seems to have changed

This protocol has no read-back, so the integration cannot confirm what the
panel did. Before assuming it failed:

- Confirm an installer code is set in this integration's options,
  Configure, Installer code. Without it, field programming is disabled.
- Check Last programming result on the device. `Accepted` means the
  Envisalink acknowledged every keystroke; anything else names the reason
  in its `detail` attribute. If you used the action rather than the
  buttons, the refusal is in the response to the call and in the log.
- Verify at the physical keypad. Installer code + `#` + `56` opens the
  review-only zone programming menu, which walks the current values without
  changing anything. That is the only way to confirm a field-programming
  change took.

See [Safety](README.md#safety-read-this) for why the confirmation gates are
where they are.
