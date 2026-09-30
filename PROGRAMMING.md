# Programming your panel: a first-time guide

This guide is for someone who has never programmed a VISTA panel. It explains the words the panel uses, what to prepare, how to make each change from Home Assistant, how to check the result at the keypad, and how to get out of trouble. The keypad procedures follow the ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide (K14488PRV3); the VISTA-20P, 15P and 10P use the same ones.

Read [Safety](README.md#safety-read-this) first. The integration cannot read the panel's settings back, so every change is checked at the keypad.

## What you can change here, and what stays at the keypad

| Change | Where |
|---|---|
| The type, partition, reporting, wiring style and response time of a board zone, a doubled zone or a zone on a wired zone expander | Device page, Program zone (action `program_zone`) |
| Exit delay, entry delay 1 and 2, auto-stay arm | Device page, Set system timing (action `set_system_timing`) |
| What the keypad's A, B, C and D keys do | Device page, Program function key (action `program_function_key`) |
| Wireless (5800-series) zones and buttons, enrolling a transmitter | Keypad, `*56` |
| Zone names shown on the keypad | Keypad, `*82` |
| Relays and outputs, user codes, the communicator and phone settings | Keypad, or an installer's downloader software |

A zone's number tells you what it is. On a VISTA-21iP or 20P:

| Zones | What they are |
|---|---|
| 1 to 8 | Wired to the panel board |
| 10 to 16 | With zone doubling on, the second sensor on board zones 2 to 8 (zone 2 pairs with 10, zone 8 with 16); zone 9 does not exist and zones 9 to 16 are unavailable for anything else |
| 9 to 48 | Zone expanders (4219/4229, eight zones each: module 1 zones 9 to 16, module 2 zones 17 to 24, and so on), or wireless (5800-series) transmitters |
| 49 to 64 | Wireless buttons (key fobs) |

The VISTA-15P has board zones 1 to 6, expansion zones 9 to 34 and buttons 49 to 56, and no zone doubling. The VISTA-10P has board zones 1 to 6, wireless zones 9 to 24 and buttons 49 to 56.

The panel asks different questions for each kind of zone, and nothing can read its menu back, so guided programming refuses any zone whose questions it cannot be sure of:

| Zone | Guided programming |
|---|---|
| A board zone | Sets type, partition, reporting, wiring style and response time. |
| A doubled zone (10 to 16, zone doubling on) | Sets type, partition and reporting. Its wiring and response time follow its board zone. |
| An expansion zone on a wired zone expander | Sets type, partition and reporting, once you state it is wired (Zone connection). |
| A wireless zone or button | Refused: the transmitter's serial number is enrolled at the keypad, so the zone is changed there. |
| Zones 9 to 16 on a 21iP or 20P | Refused until Zone doubling is stated in the integration's options (see [Before you start](#before-you-start)). |

To tell whether zone doubling is on, run the keypad check below on zones 2 to 8: HW shows each one's hardwire type, and zone doubling is type 3, ZD. Zones 10 to 16 reporting in Home Assistant while no zone expander is fitted point the same way.

## Words you will see

| Word | Meaning |
|---|---|
| Installer code | The four-digit code that opens programming. Factory default 4112; an alarm company often changes it. Different from the codes you arm and disarm with. |
| User code, master code | Codes for arming and disarming. They do not open programming. |
| Program Mode | The panel's settings mode, opened with the installer code followed by `800`. While it is open, most keypad functions, disarming included, are unavailable until you leave. |
| Data field | One numbered setting, such as `*34` (exit delay). `*` plus the number goes to it to change it; `#` plus the number shows it without changing it. |
| Zone | One input: a door contact, a window contact, a motion detector, a smoke detector. Each has a number. |
| Zone type | What the panel does when that zone opens: delay, alarm at once, ignore when home, always on for fire. |
| Partition | A separately armed area. Most homes have one. |
| Report code | Whether the zone's alarms go to the monitoring station. |
| Entry delay, exit delay | Seconds to disarm after coming in through an entry door, and to leave after arming. |
| End-of-line (EOL) resistor | A resistor at the sensor that lets the panel tell a cut wire from a closed door. The standard wiring. |
| TPI | The Envisalink's local protocol. It carries keystrokes and status, never the panel's settings. |

## Before you start

1. Find your installer code. Try the factory default 4112 first. If it does not open Program Mode and nobody knows the code, [the power-up method](#getting-out-of-trouble) still gets in.
2. Choose a time when the alarm is disarmed and nobody depends on it. A change takes seconds, and the keypad is unavailable while it runs.
3. If a monitoring company watches the panel, ask them to put the account on test while you work, and tell them afterwards which zones changed type or reporting.
4. Know which zone number is which device. With the system disarmed, open a door or walk past a motion detector and watch which zone sensor in Home Assistant turns on.
5. Write down what each zone is set to now, using [the keypad check](#check-the-result-at-the-keypad), and download diagnostics from the integration's entry. Nothing can read the panel's settings back later.
6. Add the installer code: Settings, Devices & services, Envisalink Field Programmer, Configure, Installer code. Programming stays off until it is set.
7. On a VISTA-21iP or 20P, set Zone doubling in the same form: On or Off, from the keypad check of zones 2 to 8. Zones 9 to 16 are refused while it says Not stated.

## Choosing a zone type

The names below are the ones the device page's Zone type list shows.

| The device | Zone type | Why |
|---|---|---|
| The door you normally come in through | Entry/Exit (primary) | Starts entry delay 1, so you can reach the keypad. |
| A second entry door farther from the keypad (garage, back door) | Entry/Exit (secondary) | Starts entry delay 2, which can be longer. |
| Windows, and doors nobody enters through | Perimeter (instant) | Alarms the moment it opens while armed. |
| A motion detector or inner door on the path from the entry door to the keypad | Interior (follower) | Waits out the entry delay if an entry door opened first, otherwise alarms at once. Ignored when armed Stay. |
| A motion detector that should always give the entry delay when armed Away | Interior with delay | Always gives the entry delay. Ignored when armed Stay. |
| A wired smoke or heat detector | Fire (smoke/heat detector) or Fire with verification | Always on, cannot be bypassed. Verification resets the detector and waits for a second alarm within 90 seconds before sounding. |
| A carbon monoxide detector | Carbon monoxide detector | Always on, cannot be bypassed. |
| A water leak or temperature sensor | Auxiliary alarm (24-hour) or Monitor (trouble only, no alarm) | Auxiliary beeps the keypad and reports, without the siren. Monitor reports a trouble, not an alarm. |
| An emergency button | Panic button (audible) or Panic button (silent) | Audible sounds the siren; silent reports only. |
| A contact that should only drive a chime or relay | No alarm response | Never causes an alarm. |
| A zone no longer in use | Not used | Nothing happens when it opens. |

Fire and carbon monoxide types need the Confirm life-safety zone type switch as well. Changing a smoke or CO detector's zone to any other type stops the panel responding to it, and nothing in Home Assistant can show that it happened.

## Wiring style and response time

These apply to board zones. Leave them as they are unless you know how the zone is wired.

| Setting | Guidance |
|---|---|
| Zone hardwire type (zones 2 to 8; 2 to 6 on the 15P; 1 to 6 on the 10P) | Must match the wiring. End-of-line resistor is the standard; normally closed and normally open have no resistor; zone doubling puts two sensors on one input; double-balanced is a tamper-resistant variant. A mismatch makes the zone read open or closed when it is not. Zone 1 on the 21iP, 20P and 15P is always end-of-line. Zone doubling and double-balanced exist on the 21iP and 20P only, and zone doubling is accepted only while the Zone doubling option is On, because it changes what zones 9 to 16 are. |
| Zone response time (board zones) | How long the circuit must stay open before the panel counts it: 10 ms, 350 ms, 700 ms or 1.2 seconds. Keep the zone's current value, which the keypad check shows as RT 0 to 3; the longer times ride out a noisy circuit. A doubled zone uses its board zone's response time. |

Doubled zones and expansion zones take neither setting.

## Change a zone's type

Settings, Devices & services, Envisalink Field Programmer, then the panel device. The fields are in the Configuration section. Setting them sends nothing to the panel.

1. Zone to program: the zone number.
2. Zone type: from [the table above](#choosing-a-zone-type).
3. Zone partition: Partition 1, unless your panel is partitioned.
4. Zone reports to monitoring station: on, unless the zone should never report.
5. Zone hardwire type and Zone response time: only for board zones, and only if they need to change.
6. Zone connection: for an expansion zone (9 and up, not a doubled zone), Wired, on a zone expander. It clears itself after every press, like the Confirm switches.
7. Turn on Confirm programming. For a fire or CO type, also turn on Confirm life-safety zone type.
8. Press Program zone.

The Confirm switches turn themselves off after the press, so each write needs a fresh confirmation. Last programming result, under Diagnostic, shows what happened:

| Result | Meaning |
|---|---|
| Accepted | The Envisalink acknowledged every keystroke. Check the zone at the keypad; nothing else can confirm what the panel stored. |
| Refused before sending | Nothing reached the panel. The `detail` attribute names the reason: a confirmation not on, a field not set, no installer code, Zone doubling not stated, a zone that is wireless or does not exist on the model. [TROUBLESHOOTING.md](TROUBLESHOOTING.md#last-programming-result-says-refused-before-sending) lists each one. |
| Failed while sending | The sequence stopped part-way. Go to the keypad, leave Program Mode with `*99` if it shows programming, and check the zone. |

The same change from an automation or script is the `program_zone` action; the [README](README.md#envisalink_field_programmerprogram_zone) lists its fields.

## Change the exit or entry delay

1. Timing field: Exit delay, Entry delay 1 (primary door), Entry delay 2 (secondary door), or Auto-stay arm.
2. Timing value, checked when you press the button:

| Field | Values | Factory default |
|---|---|---|
| Exit delay | 0 to 96 seconds, or 97 for 120 seconds | 60 |
| Entry delay 1, Entry delay 2 | 0 to 96 seconds, or 97, 98, 99 for 120, 180, 240 seconds | 30 |
| Auto-stay arm | 0 off, 1 partition 1, 2 partition 2, 3 both | 3 |

Auto-stay arm switches an Away arming to Stay when nobody opens an entry door during the exit delay.

3. Turn on Confirm programming and press Set system timing.

## Set a keypad function key

The A, B, C and D keys on the keypad can run one function each.

1. Function key: Key A to Key D.
2. Function key action: for example Arm Away, Arm Stay, Show the time. "Default emergency key" puts the key back to its factory emergency function.
3. Function key partition: Partition 1 on a single-partition panel.
4. Turn on Confirm programming and press Program function key.
5. Press the key at the keypad to check it does what you chose.

## Check the result at the keypad

Every check starts by opening Program Mode: type the installer code, then `800`. The keypad shows a field number instead of the usual status.

| To see | Keys | What you get |
|---|---|---|
| A zone | `*58`, then `0` `*` (no transmitter confirmation), then the zone number and `*` | One line: Zn (zone), ZT (zone type number), P (partition), RC (report code, 00 means not reported), then HW and RT (wiring and response time; EL under HW is end-of-line) for board zones, or IN (input type: AW wired, RF, UR or BR wireless) for zones 9 and up. Press `#` to back out without saving, then `00` `*` to leave the zone menu. |
| A delay | `#34` exit delay, `#35` entry delay 1, `#36` entry delay 2, `#84` auto-stay arm | The field's current value. `#` shows a field without changing it. |

Leave Program Mode with `*99`. The keypad returns to its normal display.

Zone-type numbers on the summary line for the types the device page offers: 00 not used, 01 entry/exit primary, 02 entry/exit secondary, 03 perimeter, 04 interior follower, 06 silent panic, 07 audible panic, 08 24-hour auxiliary, 09 fire, 10 interior with delay, 12 monitor, 14 carbon monoxide, 16 fire with verification, 23 no alarm response, 24 silent burglary.

## Getting out of trouble

| What you see | What to do |
|---|---|
| The keypad still shows field numbers after a change | Type `*99` to leave Program Mode. |
| `EE` or `ENTRY ERROR` | The field number typed does not exist. Type a valid one, or `*99` to leave. |
| `OC` | The keypad has lost contact with the panel. Check the keypad wiring before anything else. |
| Installer code followed by `800` does nothing | The code is not the installer code, or programming was last left with `*98`, which locks the code out. Use the power-up method below. |
| `Busy Standby` or `dI` for about a minute after power returns | Normal start-up while sensors settle. `#0` skips the wait. |

The power-up method: remove all power from the panel (unplug its transformer and disconnect its backup battery), restore it, and within 50 seconds press `*` and `#` together on the keypad. The panel opens Program Mode without the installer code. This is the only way back in after `*98`.

Two keys to avoid while in Program Mode:

| Keys | Effect |
|---|---|
| `*97` | Resets every data field to its factory default value. |
| `*98` | Leaves Program Mode and locks out the installer code until the panel is powered down and back up. Leave with `*99` instead. |

The integration itself always leaves with `*99`.
