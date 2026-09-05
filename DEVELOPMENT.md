# Development environment notes

How this repo's dev/test environment was actually built, and how to
recreate it from scratch on a fresh machine (or debug it when something
about the test setup itself seems broken, as opposed to the integration
code). Written from a Windows dev box; adjust activation commands if
you're on Linux/Mac.

## Python version: 3.14, and what Windows can and cannot run

```bash
py install 3.14          # if not already installed
py -3.14 -m venv venv
source venv/Scripts/activate    # venv/bin/activate on Linux/Mac
pip install "pytest-homeassistant-custom-component==0.13.357" \
            "mypy==1.18.2" "ruff==0.15.21"
```

Home Assistant 2026.x needs Python 3.14, and harness 0.13.357 pins Home
Assistant 2026.8.3 and brings pytest, pytest-cov and their asyncio and
aiohttp plugins with it. That is the same pin the `Tests` workflow installs,
so the local venv and CI resolve to the same versions.

**The Home Assistant layer cannot run on Windows.** `homeassistant/runner.py`
imports `fcntl`, which exists only on POSIX, and the harness's pytest plugin
imports it at plugin-load time. So in a Windows venv that has the harness,
`python -m pytest tests -q` dies inside pytest's plugin loading with
`ModuleNotFoundError: No module named 'fcntl'` before a single test is
collected -- nothing about this repo's code, and nothing that can be worked
around here. Two ways to run tests on Windows, both clean:

```bash
venv/Scripts/python -m pytest tests -q --ignore=tests/ha -p no:homeassistant
python -m pytest tests -q       # any interpreter WITHOUT the harness
```

The first turns the plugin off, the second never loads it and lets
`tests/ha/conftest.py` skip that directory on its `importorskip`. Both run
the 70 pure tests. `tests/ha` (107 tests, the coverage gate and `mypy
--strict`) is verified by the GitHub `Tests` workflow on Linux, and that run
is the one that counts. The venv is still worth having on Windows for mypy,
which reads Home Assistant's source rather than importing it.

## Test layout: a pure suite and a Home Assistant layer

`tests/` holds the pure tests: the TPI client, the models, the state
machine and the field-programming keystroke builders. None of those
modules imports Home Assistant, but the package `__init__` does, so the
pure tests load them by path through `tests/pure.py` and run on a bare
interpreter (`python -m pytest tests -q` passes 70 and skips `tests/ha`
when the harness is absent; CI, and Windows venvs that have the harness,
run them with `-p no:homeassistant` so the harness plugin cannot
interfere). `tests/ha/` holds everything that
needs `pytest-homeassistant-custom-component`: config flow, setup and
unload, entities, the actions, diagnostics. Its `conftest.py` skips the
whole directory when the harness is not installed.

## Why `tests/ha/conftest.py` does two unusual things

Both are explained inline in the file itself, but the short version:

1. **It mirrors `custom_components/envisalink_field_programmer/` into the test harness's
   own `testing_config/custom_components/` directory** before the session
   starts. `pytest-homeassistant-custom-component`'s `enable_custom_integrations`
   fixture only looks for custom integrations under its own bundled
   `testing_config/` path (see
   `pytest_homeassistant_custom_component.common.get_test_config_dir`), not
   under this repo's `custom_components/`. Without the mirror step, `hass`
   fixture tests can't find/load `envisalink_field_programmer` at all.

2. **It neuters `pytest_socket.disable_socket`** at module-import time. The
   harness calls `pytest_socket.disable_socket(allow_unix_socket=True)`
   before every test. On Windows, `asyncio`'s `ProactorEventLoop` needs a
   real `AF_INET` socketpair just to construct its self-pipe -- unix
   sockets don't cover it -- so with the guard active, **creating any new
   event loop at all fails** before any test code runs. Our tests also open
   real loopback TCP connections against an in-process fake Envisalink
   server (`tests/helpers.py::FakeEnvisalinkServer`), which the guard would
   also block. If you see `pytest_socket.SocketBlockedError` wrapped in an
   `asyncio.proactor_events` traceback, this is almost certainly it --
   confirm the neutering line is still present and runs at import time (not
   inside a fixture, which would be too late).

## A second, related Windows/asyncio gotcha: `Server.wait_closed()`

`tests/helpers.py::FakeEnvisalinkServer.stop()` deliberately does **not**
call `await self._server.wait_closed()` after `self._server.close()`. On
Python 3.12+, `wait_closed()` blocks until every *accepted connection's*
transport has fully detached, not just the listening socket. Our
`EnvisalinkClient.disconnect()` cancels its read task and closes its writer
without awaiting that cancellation settling, so the detach can lag behind
`disconnect()` returning. Chaining tests that each spin up a fresh
`FakeEnvisalinkServer` would then intermittently hang for the whole test
session with no error message, only by never reaching a final "N passed"
summary line. If you add a new fixture/helper that manages its own asyncio
server, don't await `wait_closed()` unless you specifically need to
guarantee full connection teardown before proceeding.

If you ever see a test run hang with no output past the last `PASSED`
line: reproduce with `pytest -v -s <path> 2>&1 | tail -80` and look for
repeating `"reconnect attempt failed"` log lines -- that's the signature of
a coordinator's background reconnect loop never getting cancelled, which
these two gotchas can both cause indirectly.

## Running tests, lint, mypy and the validator

```bash
python -m pytest tests -q                 # pure suite; tests/ha skips without the harness
ruff check . && ruff format --check .
venv/Scripts/python -m mypy custom_components/envisalink_field_programmer
python tools/validate_local.py
```

Clean on Windows means `70 passed, 1 skipped`: the skip is `tests/ha` on its
`importorskip`. Run the pytest line from an interpreter that does not carry
the harness, or add `--ignore=tests/ha -p no:homeassistant` if it does; see
the interpreter section above for why. On Linux the same line runs both
suites, 177 tests.

`mypy --strict` only means something with Home Assistant installed in the
interpreter running it: without it every Home Assistant class is `Any`,
so subclassing an entity and decorating with `@callback` are reported
and the real checks are skipped. Run it from the venv that has the
harness. `.github/workflows/tests.yml` runs all four steps on every push
with Home Assistant 2026.8 on Python 3.14, with `pytest-cov` reporting
coverage for `tests/ha`; that run is the one that counts.

`tools/validate_local.py` is the offline stand-in for hassfest and the
cross-file checks nothing else does: `services.yaml` and the README
against the action names in `const.py`, every translated exception key
against `strings.json`, `strings.json` against `translations/en.json`,
the manifest against the components the code imports,
`quality_scale.yaml` against the pinned list of 54 rules, the four
`brand/` PNGs against the sizes home-assistant/brands requires, and the
`hacs.json` Home Assistant floor against 2026.3.0. The floor is compared
as parsed integers, not as text -- as strings `"2026.10.0"` sorts below
`"2026.3.0"`, so a string comparison would reject a raised floor. Run it
before a push.

## hassfest / HACS validation: why they're not run locally

`hassfest` (Home Assistant's manifest/structure validator) lives in
`home-assistant/core`'s `script/hassfest/`, not in the `homeassistant` PyPI
package. Getting it running locally was attempted via a sparse git clone:

```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/home-assistant/core.git ha-core-sparse
cd ha-core-sparse
git sparse-checkout set --skip-checks script homeassistant/const.py homeassistant/__init__.py homeassistant/loader.py
python -m script.hassfest --integration-path /path/to/ha-envisalink-field-programmer/custom_components/envisalink_field_programmer
```

This got hassfest's source without a full ~1GB checkout, but **failed with
a `NameError` inside hassfest's own `model.py`** -- hassfest at the tip of
`main` was version-skewed against the `homeassistant` package the venv had
installed at the time (whatever `pytest-homeassistant-custom-component`
pinned; it is 2026.8.3 today), and
depends on newer language/stdlib behavior not worth chasing for a one-off
local check. Manifest/services.yaml/strings.json were instead reviewed by
hand against hassfest's known rules (see the CI workflow's `validate-*`
jobs, which run the *actual, version-matched* `home-assistant/actions/hassfest`
and `hacs/action` GitHub Actions on every push -- that's the real
authoritative check, not a local approximation). If you want to re-attempt
a local run, you'd need to either check out core at a tag matching the
installed `homeassistant` version, or bump the venv's `homeassistant`
pinned version to something closer to current `main`.

## The programming form (no frontend build)

There is no JavaScript in this repository and no build step. Up to 0.3.1 the
guided programming UI was a bundled Lovelace card (TypeScript + Lit, built with
esbuild, the output committed into the integration and registered as a frontend
resource at setup). 0.4.0 removed all of it: the fields are entities on the
panel device instead, so a user finds them where every other integration puts
its settings and nobody has to add a card.

The form lives in three places:

- `field_programming.py` holds `ProgrammingForm`, the values, and
  `ProgrammingResult`, the outcome of the last press. Both hang off the
  coordinator, so every entity of an entry reads and writes the same object.
- `number.py`, `select.py` and `switch.py` are the fields. Setting one writes
  to the form and calls `async_write_ha_state()`. None of them touches the
  panel.
- `button.py` is the only thing that sends. It checks the confirm switch and
  the required values, calls the matching `async_program_*` coroutine in
  `field_programming_services.py` -- the same one the action calls -- records
  the result, clears the confirmations, and calls
  `coordinator.async_update_listeners()` so the switches and the result sensor
  redraw.

Adding a field means: the attribute on `ProgrammingForm`, the entity in its
platform, the name (and any option names) in `strings.json`, an icon in
`icons.json`, and the read in the button. `tools/validate_local.py` fails a
name or icon that matches no entity, and an entity whose name is not declared.

## Real-hardware gotcha: only one TPI client at a time

Confirmed 2026-07-04 against a live Envisalink EVL-4 + VISTA-21iP: setting
up this integration while `envisalink_new` (or anything else) already holds
a TPI connection to the same device fails with a plain "Could not connect
to the Envisalink at that host/port" -- indistinguishable in the config
flow's error handling from a genuinely wrong host/port. Root cause is the
Envisalink's own TPI server, which accepts exactly one client connection on
port 4025 and refuses any second one outright (this matches the TPI spec's
"will only accept one client connection on that port" line, but it's easy
to forget when troubleshooting a "cannot_connect" error and go looking for
a networking problem instead).

**Diagnostic shortcut**: if another Envisalink integration is already
configured on the same HA instance, check its config entry's `disabled_by`
field in `.storage/core.config_entries` (or just check the UI) before
assuming the new integration's host/port/password are wrong -- if that
other entry isn't disabled, that's almost certainly the actual cause, and
no amount of double-checking credentials will fix it.

## Protocol correction: the original TPI research was wrong

**This is still TPI.** The correction described here is not a switch to some
different, unrelated protocol -- the Envisalink has always spoken (and
still speaks) TPI (Third Party Interface) on port 4025, and this
integration has always used TPI. What changed is the accuracy of this
integration's understanding of TPI's wire-level framing details, nothing
about which protocol/port/system it connects to.

The client (`client.py`), state machine (`state_machine.py`), and the
relevant parts of `const.py` were originally built from the "EnvisaLink TPI
Programmer's Document v1.08" (2017-02-10) PDF, which describes a real
variant of TPI: hex-ASCII, checksum-framed, with 3-digit numeric command
codes and a `005`/`505`-style login handshake.

That does not match what a real EVL-4 + VISTA-21iP actually speaks -- same
protocol name, different (and, for this hardware, incorrect) wire format.
This was discovered during live-hardware testing (2026-07-04): after the
config flow failed with "Could not connect", Home Assistant's core log
showed

```
TPIProtocolError: checksum mismatch for 'Login:': got n:, expected 8B
```

i.e. the device was sending the literal text `Login:` rather than the
framed/checksummed handshake the client expected. Direct raw-socket testing
(via SSH into the HA host and a short Python script) confirmed the real
sequence: the EVL sends `Login:\r\n`, expects just the plain-text password
in response (no framing, no checksum), then replies `OK\r\n` / `FAILED\r\n`
/ `Timed Out!\r\n`. Every message after that is `%CODE,DATA$` (EVL ->
client) or `^CODE,DATA$` (client -> EVL), terminated by `$`, with no
checksum at all -- and keystrokes go one character per frame
(`^03,<partition>,<char>$`), not chunked.

A second, subtler wire-protocol correction landed later, found because
arm/disarm/away did nothing against real hardware while status and zones
worked fine: the EVL processes exactly **one command at a time**. It
acknowledges every command with `^CODE,<response>$` and rejects a command
that arrives while the previous one is still being processed with response
`01` ("Receive Buffer Overrun" -- that meaning comes straight from
`pyenvisalink`'s Honeywell response-code table, and is why that library
runs every command through a serialized queue that waits for each ack).
The original client fired keystroke frames back-to-back with no ack
handling, so single-frame commands (poll, zone timer dump) worked, but any
multi-keystroke sequence -- a user code plus arm/disarm digit, a `*1zz#`
bypass, a field-programming string -- only ever got its first keypress
onto the panel, silently. `EnvisalinkClient._send()` now serializes the
full round-trip (write, await ack, retry with backoff on buffer overrun,
raise `TPICommandError` on rejection/timeout), and terminates outbound
frames with `\r\n` after the `$` like `pyenvisalink` does.

This was cross-checked against the actively maintained `pyenvisalink`
library (the library behind `ufodone/envisalink_new`, a HACS integration
confirmed working against this exact hardware). Reference copies of its
`envisalink_base_client.py`, `honeywell_client.py`, and
`honeywell_envisalinkdefs.py` (GPL v3) were downloaded from
`https://github.com/ufodone/envisalink_new` purely to read the real field
layouts (icon-LED bitfield, CID event parsing, zone timer dump math) --
same handling as the Vista Programming Guide PDF: read for reference, then
**deleted, not committed** (`_scratch_honeywell_client.py`,
`_scratch_honeywell_envisalinkdefs.py`, `_scratch_envisalink_base_client.py`
in the repo root during this work). Every module this integration ships
paraphrases the protocol's *meaning* in its own words and implementation,
it does not contain copied `pyenvisalink` source.

What carried over unchanged from the incorrect version: the Vista
`*56`/`*57`/`*99` field-programming **keystroke language** itself
(`field_programming.py`, `programming.py`'s Program Mode guard) -- that
part was always just a string of keystrokes to type at a keypad, and is
independent of how those keystrokes get framed on the wire.

What changed as a result, in one place, for anyone debugging against this
history:
- `client.py`: full rewrite of the login handshake and frame parsing/building.
- `const.py`: the `COMMAND_SCHEMA`/`COMMAND_NAMES` 3-digit numeric event
  codes were replaced with the real `%00`/`%01`/`%02`/`%03`/`%20`/`%FF`
  event codes and `^00`-`^03` command codes.
- `state_machine.py`: rewritten around icon-LED bitfield decoding (`%00`)
  and the zone timer dump (`%FF`) as the only two real data sources for a
  Honeywell panel, instead of the ~30 distinct numeric event codes the old
  (wrong) protocol claimed to have.
- `coordinator.py`/`alarm_control_panel.py`: arm/disarm/arm-stay/arm-night
  now all send the user code plus a mode digit as keystrokes (matching a
  real keypad) instead of calling dedicated arm/disarm commands that don't
  exist on the wire; all four now require a code, not just disarm.
- `models.py`: several fields tied to event codes the real protocol doesn't
  have (`force_arm_enabled`, `busy`, `keypad_lockout`, `failed_to_arm`,
  distinct AC/battery/bell/FTC/tamper system trouble types, entry delay,
  per-zone alarm/tamper/fault) were dropped rather than faked; per-zone
  bypass tracking became a best-effort local flag (see the module
  docstring) since the real protocol has no per-zone bypass event without
  alpha-text parsing this integration deliberately avoids.

## Where the Vista programming-guide research came from

The field-programming data model (`field_programming.py`) was built from
the **ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3 10/12
Rev B**, fetched during development from
`https://advancedsecurityllc.com/wp-content/uploads/2024/05/Honeywell-Vista-21ip-Programming-Guide.pdf`
(a mirror; search "Vista-21ip Programming Guide K14488PRV3" if that link
ever goes dead -- several alarm-dealer sites mirror the same Honeywell PDF).
Extracted locally with `pypdf` (`pip install pypdf cryptography` -- the PDF
has an owner-password restriction that needs `cryptography` for pypdf's AES
handling) since the sandboxed environment lacked `poppler-utils` for the
`Read` tool's built-in PDF page rendering:

```python
from pypdf import PdfReader
r = PdfReader("vista21ip_programming_guide.pdf")
text = "\n".join(page.extract_text() for page in r.pages)
```

The downloaded PDF and extracted text were deleted after use (not
committed -- it's Honeywell's copyrighted material); `field_programming.py`
paraphrases the field meanings in its own words rather than quoting the
manual, and cites the exact document name/revision in its module
docstring so the source can be re-fetched and cross-checked if the field
model is ever in doubt.

The EyezOn/Envisalink brand colors (used by the removed card, and still by the
brand images in `brand/`) came from fetching
`https://www.eyezon.com/assets/css/main.min.css` directly and grepping for
`--*-accent-*` custom properties and their hex values, rather than trusting a
generic web search (which turned up nothing useful) or visual inspection
(`WebFetch` strips CSS from rendered pages).

## Adding or promoting a panel model

Panel support lives in `custom_components/envisalink_field_programmer/panels/`:

- `base.py` — the `PanelDialect` protocol, the `PanelModel` dataclass, and the
  `Verification` enum (`VERIFIED` / `GRAMMAR_VERIFIED` / `PROVISIONAL`).
- `vista.py` / `dsc.py` — one dialect per family plus that family's model
  registry. A dialect is data + a few small methods (program-mode wrapper,
  zone-type table, and `opens_program_mode()` for the safety guard).
- `__init__.py` — the combined registry and `get_model()` / `get_dialect()`
  lookups (canonical id, aliases, and punctuation-insensitive matching).

To **add a model within an existing family**, append a `PanelModel` to that
family's registry with an honest `verification` level and `notes`. To **promote**
a model from Provisional/Grammar-verified to Verified, check its field numbers
and zone-type codes against that panel's own programming guide (same method as
the original 21iP work — see the previous section), correct anything the family
default gets wrong, and only then bump its `verification`.

Two safety invariants the tests enforce (`tests/ha/test_panels.py`), keep them:

- Only genuinely-verified models carry `Verification.VERIFIED`. The guided
  services refuse anything less without an explicit `confirm_unverified_model`.
- The keystroke guard is family-aware: each dialect's `opens_program_mode()`
  must match that family's real installer-mode trigger (VISTA `<code>800`, DSC
  `*8<code>`) and *not* the other family's, so the guard can't be bypassed by
  selecting the wrong dialect. Prefer an over-cautious false positive to a miss.

## Guided-programming capabilities per dialect

Guided programming is expressed per *operation*, not as one on/off switch. A
dialect declares `supported_guided_ops: frozenset[GuidedOp]` (subset of
`ZONE`, `TIMING`, `FUNCTION_KEY`), and each service refuses an operation the
dialect doesn't list:

- **Residential VISTA** supports all three (`*56` zones, `*34`-style timing,
  `*57` function keys).
- **Commercial VISTA** (`CommercialVistaDialect`, `dialect_id="vista_commercial"`
  on the 128BP/250BP) supports **TIMING only** — `<code>8000` entry and the
  partition-specific `*09`-`*12` fields. Its `#93` zone menu is deeply
  conditional and is deliberately not driven without hardware.
- **DSC** supports **none** yet: the section keystroke builders
  (`build_dsc_zone_definitions`, `build_dsc_partition_timing`) are pure,
  unit-tested functions, but the client transport is Honeywell-TPI-only, so
  there's no path to send them. Wiring DSC needs a DSC transport handler + a DSC
  fake server, then real-hardware verification before flipping on any GuidedOp.

A model normally uses its family's dialect; set `PanelModel.dialect_id` to point
at a different one (as the commercial VISTA models do). Timing is dialect-owned:
`timing_fields()` lists the valid field ids and `build_timing_keystrokes(field,
value, partition)` does the translation + range validation, so the
`set_system_timing` service stays panel-agnostic.
