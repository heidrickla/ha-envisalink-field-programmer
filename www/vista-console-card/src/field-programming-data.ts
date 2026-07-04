/**
 * Mirrors custom_components/vista_console/field_programming.py.
 *
 * This is presentation data only (labels/descriptions/valid ranges for the
 * guided UI) -- the backend re-validates everything independently and is
 * the actual source of truth. Keep these two files in sync by hand; there
 * is no shared source between the Python and TypeScript sides.
 */

export interface ZoneTypeInfo {
  code: number;
  label: string;
  description: string;
  category: string;
  lifeSafety: boolean;
}

export const ZONE_TYPES: ZoneTypeInfo[] = [
  { code: 0, label: "Not used", description: "This zone number has nothing assigned to it.", category: "Special", lifeSafety: false },
  { code: 1, label: "Entry/Exit (primary)", description: "Your main door. Gives you time to walk out after arming, and time to walk in and disarm before an alarm sounds.", category: "Entry/Exit", lifeSafety: false },
  { code: 2, label: "Entry/Exit (secondary)", description: "A second, less-used entry door that needs more time to get to the keypad than your main door.", category: "Entry/Exit", lifeSafety: false },
  { code: 3, label: "Perimeter (instant)", description: "An exterior door or window that should alarm immediately the moment it opens while armed -- no walk-in delay.", category: "Perimeter / Interior", lifeSafety: false },
  { code: 4, label: "Interior (follower)", description: "An indoor area you pass through after entering (foyer, hallway). Delayed only if a delay door was opened first; otherwise instant. Auto-ignored when armed Stay/Instant.", category: "Perimeter / Interior", lifeSafety: false },
  { code: 9, label: "Fire (smoke/heat detector)", description: "A hardwired smoke or heat detector. Always active, day or night, armed or not, and cannot be bypassed. Changing a real smoke detector's zone away from this type will silence it.", category: "Life Safety", lifeSafety: true },
  { code: 16, label: "Fire with verification", description: "Like Fire, but the panel double-checks before sounding, to cut down on false alarms. Always active and cannot be bypassed.", category: "Life Safety", lifeSafety: true },
  { code: 14, label: "Carbon monoxide detector", description: "A CO detector. Always active and cannot be bypassed.", category: "Life Safety", lifeSafety: true },
  { code: 6, label: "Panic button (silent)", description: "An emergency button. Notifies the monitoring station only -- no sound at the keypad or siren.", category: "Panic / Emergency", lifeSafety: false },
  { code: 7, label: "Panic button (audible)", description: "An emergency button. Notifies the monitoring station and sounds the keypad and siren.", category: "Panic / Emergency", lifeSafety: false },
  { code: 8, label: "Auxiliary alarm (24-hour)", description: "For an emergency button or a monitoring sensor (water, temperature). Notifies the monitoring station and beeps the keypad, but does not sound the siren.", category: "Panic / Emergency", lifeSafety: false },
  { code: 10, label: "Interior with delay", description: "Like Interior (follower), but always gives the entry delay when armed Away, even if no delay door was tripped first.", category: "Perimeter / Interior", lifeSafety: false },
  { code: 12, label: "Monitor (trouble only, no alarm)", description: "Reports faults as a non-alarm 'trouble' condition, not a burglary alarm. Do not pair with a relay set to trigger on alarm.", category: "Special", lifeSafety: false },
  { code: 23, label: "No alarm response", description: "Never triggers an alarm by itself -- useful for an output relay action with no security response.", category: "Special", lifeSafety: false },
  { code: 24, label: "Silent burglary", description: "Like Perimeter, but with no audible indication anywhere -- only a silent report to the monitoring station.", category: "Perimeter / Interior", lifeSafety: false },
];

export const ZONE_TYPES_BY_CODE: Record<number, ZoneTypeInfo> = Object.fromEntries(
  ZONE_TYPES.map((z) => [z.code, z])
);

export const HARDWIRE_TYPES: { value: string; label: string }[] = [
  { value: "0", label: "End-of-line resistor (standard, most common)" },
  { value: "1", label: "Normally closed, no resistor" },
  { value: "2", label: "Normally open, no resistor" },
  { value: "3", label: "Zone doubling (two zones share one input)" },
  { value: "4", label: "Double-balanced (tamper-resistant)" },
];

export const RESPONSE_TIMES: { value: string; label: string }[] = [
  { value: "0", label: "10 ms (fastest, standard wired contacts)" },
  { value: "1", label: "350 ms" },
  { value: "2", label: "700 ms" },
  { value: "3", label: "1.2 seconds (slowest, reduces false trips)" },
];

export interface SystemTimingFieldInfo {
  field: string;
  label: string;
  description: string;
  min: number;
  max: number;
  specials: Record<number, string>;
}

export const SYSTEM_TIMING_FIELDS: SystemTimingFieldInfo[] = [
  {
    field: "34",
    label: "Exit delay",
    description:
      "How many seconds you have to leave after arming before the exit delay ends. Factory default is 60.",
    min: 0,
    max: 96,
    specials: { 97: "120 seconds" },
  },
  {
    field: "35",
    label: "Entry delay 1 (primary door)",
    description:
      "How many seconds you have to disarm after opening the primary entry door. Factory default is 30.",
    min: 0,
    max: 96,
    specials: { 97: "120 seconds", 98: "180 seconds", 99: "240 seconds" },
  },
  {
    field: "36",
    label: "Entry delay 2 (secondary door)",
    description: "Same as Entry Delay 1, but for secondary entry/exit zones. Factory default is 30.",
    min: 0,
    max: 96,
    specials: { 97: "120 seconds", 98: "180 seconds", 99: "240 seconds" },
  },
  {
    field: "84",
    label: "Auto-stay arm",
    description:
      "If no delay zone is opened during exit delay, automatically switch the arming mode to Stay. 0=off, 1=partition 1 only, 2=partition 2 only, 3=both. Factory default is 3.",
    min: 0,
    max: 3,
    specials: {},
  },
];

export interface FunctionKeyActionInfo {
  value: number;
  label: string;
}

export const FUNCTION_KEY_ACTIONS: FunctionKeyActionInfo[] = [
  { value: 0, label: "Default emergency key (fire/police/medical)" },
  { value: 1, label: "Page a number" },
  { value: 2, label: "Show the time" },
  { value: 3, label: "Arm Away" },
  { value: 4, label: "Arm Stay" },
  { value: 5, label: "Arm Night-Stay" },
  { value: 6, label: "Step-arm (Stay, then Night, then Away)" },
  { value: 7, label: "Trigger an output/relay" },
  { value: 8, label: "Send a communication test" },
];
