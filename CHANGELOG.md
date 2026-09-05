# Changelog

Notable changes to this integration, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version
numbers follow [semantic versioning](https://semver.org/spec/v2.0.0.html).

Dates are the day the work landed on `main`, which is not the day a release
was cut.

## [0.4.1] - 2026-09-05

### Fixed

- **Refusal messages name entities the way the user sees them.** "Set X before
  pressing Y", "Y needs the Z switch on", and the life-safety and unverified-model
  refusals carried the English defaults of the button, field and switch names,
  whatever language Home Assistant runs in and whatever the user had renamed them
  to. They now read the names from the entity registry at the moment of the
  refusal.

## [0.4.0] - 2026-09-05

Field programming moves onto the panel's own device page, and the Lovelace
card that used to carry it is gone. A user should not have to know how to add
a custom card to change a zone type.

### Added

- **A configuration entity per programming field, on the panel device.** The
  zone to program, its type, partition, reporting, wiring style and response
  time; the timing field, its value and, on commercial panels, its partition;
  the function key, what it should do and its partition. Setting any of them
  changes nothing on the panel -- they are a form, held for as long as the
  entry is loaded.
- **A button per operation**: Program zone, Set system timing, Program
  function key. Each submits the current values through the same guided
  operation the action of the same name runs, so every guard is identical
  whichever way it is driven. A button refuses, saying which, when the confirm
  switch is off or a value it needs is unset.
- **A Confirm programming switch that has to be on for any write, and turns
  itself off again after every attempt** -- accepted, refused or failed. One
  confirmation authorizes exactly one write. Confirm life-safety zone type and
  Confirm unverified panel model work the same way and are spent by the same
  press; the second appears only on a model whose fields are not verified
  against its own programming guide.
- **A Last programming result diagnostic sensor** carrying the outcome
  (Accepted, Refused before sending, Failed while sending), which operation it
  was, and the reply that decided it. "Accepted" means the Envisalink
  acknowledged every keystroke, which is as far as this protocol sees; the
  panel's own opinion of what it stored is still only visible at the keypad.
- The device page offers only what the panel's dialect actually drives: a DSC
  entry gets no programming entities at all, and a commercial VISTA gets the
  timing form only, rather than buttons that always refuse.
- **Diagnostics carry the programming form and the last result**, which is
  what a report of "I programmed a zone and nothing happened" needs. No code
  is in either.

### Removed

- **The bundled `envisalink-field-programmer-card` Lovelace card**, and with
  it `frontend.py`, the committed card bundle, the `www/` source workspace,
  the `frontend` and `http` manifest dependencies, the npm build job in CI and
  the npm Dependabot job. A card placed on a dashboard shows as a missing
  custom element until it is deleted; nothing else is left behind, because the
  resource was registered at runtime and never written into a dashboard's
  resources.

### Changed

- The five actions are unchanged and still take the same fields. What moved is
  where their guards live: `field_programming_services.py` now exposes the
  three guided operations themselves, and the actions and the buttons are two
  front ends onto them.

## [0.3.1] - 2026-09-05

Everything here comes from running 0.3.0 against a real EVL-4 and a
VISTA-21iP on 2026-09-05. The Envisalink admits one TPI client at a time and
frees that slot only once it has seen the previous connection close; both
defects below were that fact going unhandled.

### Fixed

- **Reconfigure works on an entry that is loaded.** The form's connection test
  wanted the same single session the running entry was holding, so it answered
  "Could not connect" whatever was typed, and host, port, password, panel
  model and the counts could not be changed without deleting the entry. The
  entry now hands its session over for the length of the test and takes it
  back straight afterwards. A form that leaves host, port and password alone
  is not tested at all, because a login proves nothing about a changed zone
  count, and the session is left undisturbed.
- **Setup no longer races the module.** The setup form's login test
  disconnected and the entry's own connection opened four milliseconds later,
  which the module dropped part-way through the login; the entry failed and
  came up on Home Assistant's retry five seconds afterwards. Disconnecting now
  waits for the close to land, the test waits a further half second, and setup
  makes one more attempt before failing the entry. A rejected password is
  still not retried, so reauthentication is as immediate as it was.
- **A reconfigure during an outage no longer leaves the module busy.** Handing
  the session over while the entry was mid-reconnect cancelled that reconnect
  without waiting for the cancellation to land, and the socket it had already
  opened stayed open until the garbage collector reached it -- so the
  connection test could still meet a module that thought its one slot was
  taken. The handover now waits the reconnect out, and a login cancelled
  part-way through closes its own socket.
- **A dropped connection cannot be reported against the session after it.**
  The read loop's parting "connection lost" could arrive once the next
  session was already up, which started a reconnect on top of a healthy
  connection. Disconnecting now waits that loop out before returning.

### Added

- **The login handshake is logged at debug level.** The prompt the module
  sent, the length of the password being sent, whether it is plain ASCII,
  whether it has whitespace around it, and the module's answer. The password
  itself is never logged and a test enforces that. This is what tells a
  password the module rejected apart from one that never arrived intact --
  a distinction that could not be made at all while this was blind. See
  "Turning on debug logging" in the README.

## [0.3.0] - 2026-09-05

### Added

- **A brand logo.** `brand/` now ships a real landscape logo, the icon art
  beside the integration's name, at `logo.png` (504x160) and `logo@2x.png`
  (1008x320), alongside the 256x256 and 512x512 icons. Home Assistant serves
  all four out of the integration itself, so the name is drawn wherever the
  interface wants a logo rather than the icon being stretched into the space.
- **DHCP discovery.** An Envisalink that takes a lease from the `00:1C:2A`
  block (Envisacor Technologies, who make the module) is offered under
  Settings, Devices & services with its address filled in. The password still
  has to be typed, so nothing is set up unattended.
- **The entry follows a module that moves.** The MAC learned at discovery is
  stored with the entry; a later lease for that MAC at a different address
  updates the host, unique id and title and reloads the entry. An entry set up
  by hand at an address that later appears in a lease adopts the MAC then.
- **Reconfigure step.** Host, port, password, panel model and the zone and
  partition counts can be changed without deleting the entry, so entity ids
  and history survive. A blank password keeps the stored one; an address
  another entry already uses is refused.
- **Lowering a zone or partition count deletes the entities above it.** Setup
  removes the registry entries for the zones and partitions the entry no
  longer has, instead of leaving them in the entity list as unavailable
  forever. Entities below the count, and the ones that are not numbered, are
  left alone.
- **A repair issue for a session that stays down.** After five failed
  reconnects, about two and a half minutes, Settings, System, Repairs names
  the address and the usual cause, which is another client holding the
  Envisalink's single TPI session. It clears when the connection returns, and
  goes when the entry is deleted.
- **A reauthentication step.** A password the Envisalink rejects now asks for
  the current one instead of retrying forever.
- The device links to the Envisalink's own web page, and carries the module's
  MAC as a network connection once discovery has learned it.
- `icons.json`: an icon for each of the five actions and for the two
  diagnostic text sensors, which have no device class to supply one.
- Every config-flow field has a description under it explaining what to type.
- `quality_scale.yaml` records this integration against all 54 Integration
  Quality Scale rules, with a written reason on everything not done, and
  `tools/validate_local.py` checks those claims against the file set offline.
- README: removal instructions, discovery, reconfiguring, every field of every
  action, the installation and options parameters, the update model, example
  automations and troubleshooting.

### Changed

- **Entity names are translated.** Every entity takes its name from a
  translation key rather than an English literal, with the partition or zone
  number as a placeholder. A zone named in the options still shows that name
  as typed. The displayed names are unchanged, so entity ids do not move.
- **Every error message is translated**, including the keystroke-guard
  refusals and all six guided field-programming refusals. The refused
  keystroke sequence is still redacted before it is shown.
- **The actions are registered when the component loads**, not per entry, so
  calling one while the entry is unloaded gives a message naming the entry
  instead of an unknown-action error.
- **The Envisalink password and both alarm codes are password fields** and are
  never sent back to the browser. In the options a blank code field keeps the
  stored code and a remove switch clears it.
- **The Last Event sensor is disabled by default.** It changes on every
  keepalive acknowledgement, which is a state write every 30 seconds for a
  value only useful while debugging the protocol. Enable it in the entity
  settings if you want it; the bundled card does not use it.
- **System Trouble is a diagnostic entity**, alongside Last Event and Last
  User: it reports the panel's own health, not the security state.
- **Arming, disarming and zone bypass are sent one at a time.** Each writes a
  keystroke sequence and the client's lock is held per frame, so a script that
  armed two partitions at once, or a call that toggled several bypass switches
  together, could interleave their keypresses at the panel. Reads are
  unaffected and still run in parallel.
- Input mistakes in the actions are reported as validation errors without a
  traceback; a command the panel refuses is reported as a device error.
- A protocol or command failure during setup is a retry rather than an error,
  and the socket is released so the retry can log in again.
- Losing the connection logs one line at info level, and so does getting it
  back.
- The coordinator lives on the config entry rather than in `hass.data`, and
  its keepalive and reconnect tasks are tied to the entry's lifecycle.
- Minimum Home Assistant is now **2026.3**, up from 2025.2. Two releases
  matter: 2025.2 first has the DHCP discovery helper this integration
  imports, and 2026.3 is where Home Assistant began serving an integration's
  own `brand/` directory. This integration is in no brands repository, so on
  anything older it loads with no icon anywhere in the interface. HACS
  enforces the floor.

### Removed

- The old `brand/logo.png`, which was a byte-for-byte copy of the icon and
  told the interface nothing the icon did not. A real logo replaces it, and
  `tools/validate_local.py` now fails a logo whose bytes match an icon's.

### Fixed

- A failure between logging in and the first zone timer dump left the
  Envisalink's single TPI session half open, so every retry looked like an
  unreachable host.
- `tools/validate_local.py` compared the `hacs.json` Home Assistant floor as
  text, where `"2026.10.0"` sorts below `"2026.3.0"`, so raising the floor
  past 2026.9 would have failed the check. It parses the parts as integers
  now; 2026.3.0 and above pass, below it fails.

## [0.2.1] - 2026-09-04

The last tagged release, cut before the work above. See its
[release notes](https://github.com/heidrickla/ha-envisalink-field-programmer/releases/tag/v0.2.1).

## Earlier

The protocol rewrite, the panel model registry, the guided field-programming
layer and the Lovelace card predate this file. See the commit history and
`DEVELOPMENT.md` for how the TPI framing was corrected against real hardware.
