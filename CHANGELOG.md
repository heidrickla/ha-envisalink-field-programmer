# Changelog

Notable changes to this integration, newest first. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version
numbers follow [semantic versioning](https://semver.org/spec/v2.0.0.html).

Dates are the day the work landed on `main`, which is not the day a release
was cut: everything under Unreleased is on `main` and in no tag yet.

## [Unreleased] - 2026-09-05

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
