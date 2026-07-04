# This branch: archived checksum-framed TPI protocol implementation

This branch preserves the integration exactly as it stood before the
protocol rewrite on `main` (2026-07-04). It implements a **hex-ASCII,
checksum-framed** wire protocol with 3-digit numeric command codes, a
`005`/`505`-style login handshake, and dedicated arm/disarm commands
(`030`/`031`/`040`/etc.) — matching the "EnvisaLink TPI Programmer's
Document v1.08" (2017-02-10) PDF.

**Why this was set aside**: this protocol does not match a real EVL-4 +
VISTA-21iP, which was confirmed against live hardware. The real protocol
(now on `main`) is a plain-text `Login:`/`OK`/`FAILED` handshake followed by
`%CODE,DATA$` / `^CODE,DATA$` framing with no checksum at all. See `main`'s
`DEVELOPMENT.md` ("Protocol correction: the original TPI research was
wrong") for the full story of how this was discovered.

**Why this branch exists anyway**: the checksum-framed protocol implemented
here was reverse-engineered from real Envisalink documentation, not
invented — it's plausible that some Envisalink hardware/firmware revision,
or a different EyezOn product line, actually speaks this variant even
though Lewis's EVL-4 doesn't. If that ever needs investigating, this branch
is a complete, tested (as of this commit) starting point rather than
something to rebuild from scratch. Do not merge this into `main` — the two
protocols are mutually incompatible implementations of the same integration
name/domain.

If you're picking this branch up: everything else about the integration
(config flow shape, entity platforms, the field-programming keystroke
layer, the Lovelace card) is protocol-agnostic and was carried forward to
`main` largely unchanged — only `client.py`, the event/command constants in
`const.py`, `state_machine.py`, and the arm/disarm plumbing in
`coordinator.py`/`alarm_control_panel.py` differ between the two branches.
