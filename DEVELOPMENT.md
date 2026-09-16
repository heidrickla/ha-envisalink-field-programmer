# Development environment notes

How to build this repo's test environment from scratch, and what to check
when the test setup itself looks broken rather than the integration code.
Written from a Windows box; adjust the activation command on Linux or Mac.

## Python version: 3.14

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

## Running the Home Assistant suite on Windows

`homeassistant/runner.py` imports `fcntl` and `homeassistant/util/resource.py`
imports `resource`, both POSIX-only, and the harness's pytest plugin imports
`runner` at plugin-load time. Without a stand-in, `pytest` dies during plugin
loading with `ModuleNotFoundError: No module named 'fcntl'` before a test is
collected.

`tests/winposix.py` supplies both modules and two further shims:

| Blocker | Where | Stand-in |
|---|---|---|
| `import fcntl` | `homeassistant/runner.py` | module with `LOCK_EX`, `LOCK_NB` and a `flock` that does nothing; the lock file is never taken under pytest |
| `import resource` | `homeassistant/util/resource.py` | module reporting a descriptor limit already high enough to leave alone |
| `pytest_socket` refuses `socket.socketpair()` | ProactorEventLoop self-pipe | the real socket class, for the length of that one call |
| `aiodns` refuses the Proactor loop | `homeassistant.runner` loop factory | the selector loop |

`pyproject.toml` carries `addopts = "-p tests.winposix"`, and pytest handles
`-p` before entry point plugins, which is early enough for the first two.
`tests/ha/conftest.py` calls `install_ha_layer_shims()` for the last two.
This conftest also neuters `pytest_socket.disable_socket` wholesale for its
loopback connections to the fake server, which covers the socketpair case as a
side effect. Measured 2026-09-16: `212 passed` with the call, `212 passed`
with it commented out. The call stays so the suite does not rest on that side
effect. Every function returns immediately off Windows, so Linux and CI are
unchanged. No environment variable to remember:

```bash
venv/Scripts/python -m pytest tests -q
```

Observed on Windows 11 with Python 3.14.7 and Home Assistant 2026.8.3 on
2026-09-16: `212 passed`, the full suite, pure and `tests/ha` together.

Two ways to run the pure suite alone:

```bash
venv/Scripts/python -m pytest tests -q --ignore=tests/ha -p no:homeassistant
python -m pytest tests -q       # any interpreter without the harness
```

The first turns the harness plugin off and drops `tests/ha` from collection
entirely; measured 2026-09-16, it gives `81 passed`. The second never loads
the plugin and lets `tests/ha/conftest.py` skip that directory on its
`importorskip`; it gives `81 passed, 1 skipped`, the skip being `tests/ha`.

The GitHub `Tests` workflow runs the same suite on Linux with the coverage
gate and `mypy --strict`. `mypy` needs no stand-in on Windows: it reads Home
Assistant's source rather than importing it.

## Test layout: a pure suite and a Home Assistant layer

`tests/` holds the pure tests: the TPI client, the models, the state
machine and the field-programming keystroke builders. None of those
modules imports Home Assistant, but the package `__init__` does, so the
pure tests load them by path through `tests/pure.py` and run on a bare
interpreter. CI, and Windows venvs that have the harness, run them with
`-p no:homeassistant` so the harness plugin cannot interfere. `tests/ha/`
holds everything that needs `pytest-homeassistant-custom-component`: config
flow, setup and unload, entities, the actions, diagnostics. Its
`conftest.py` skips the whole directory when the harness is not installed.

## Why `tests/ha/conftest.py` does two unusual things

1. It mirrors `custom_components/envisalink_field_programmer/` into the test harness's
   own `testing_config/custom_components/` directory before the session
   starts. `pytest-homeassistant-custom-component`'s `enable_custom_integrations`
   fixture only looks for custom integrations under its own bundled
   `testing_config/` path (see
   `pytest_homeassistant_custom_component.common.get_test_config_dir`), not
   under this repo's `custom_components/`. Without the mirror step, `hass`
   fixture tests can't find/load `envisalink_field_programmer` at all.

2. It neuters `pytest_socket.disable_socket` at module-import time. The
   harness calls `pytest_socket.disable_socket(allow_unix_socket=True)`
   before every test, and these tests open real loopback TCP connections
   against an in-process fake Envisalink server
   (`tests/helpers.py::FakeEnvisalinkServer`), which the guard blocks. The
   line has to run at import time; inside a fixture is too late. A
   `pytest_socket.SocketBlockedError` in the output means it is gone or has
   moved. `tests/winposix.py` covers the same guard against the Windows
   event loop's own self-pipe, narrowly, and is what would carry the suite
   if this wholesale neutering were ever dropped.

## A second Windows and asyncio trap: `Server.wait_closed()`

`tests/helpers.py::FakeEnvisalinkServer.stop()` does not call
`await self._server.wait_closed()` after `self._server.close()`. On Python
3.12 and later, `wait_closed()` blocks until every accepted connection's
transport has fully detached, not just the listening socket.
`EnvisalinkClient.disconnect()` cancels its read task and closes its writer
without waiting for that cancellation to settle, so the detach can lag behind
`disconnect()` returning. Chained tests that each spin up a fresh
`FakeEnvisalinkServer` then hang for the whole session with no error message
and no final "N passed" line. A new fixture or helper managing its own
asyncio server should not await `wait_closed()` unless it needs full
connection teardown before proceeding.

A run that hangs with no output past the last `PASSED` line: reproduce with
`pytest -v -s <path> 2>&1 | tail -80` and look for repeating
`"reconnect attempt failed"` log lines. That is a coordinator's background
reconnect loop never getting cancelled, which both traps above can cause
indirectly.

## Running tests, lint, mypy and the validator

```bash
venv/Scripts/python -m pytest tests -q   # full suite, Windows or Linux
ruff check . && ruff format --check .
venv/Scripts/python -m mypy custom_components/envisalink_field_programmer
python tools/validate_local.py
```

Observed on 2026-09-16: `212 passed` for the full suite, `81 passed, 1
skipped` for the pure suite alone (the skip is `tests/ha` on its
`importorskip`), `Success: no issues found in 23 source files` from mypy, and
`all offline checks passed` from the validator. Coverage over both suites in
the CI order: 98.85%, 21 of 1822 statements missed.

`mypy --strict` only means something with Home Assistant installed in the
interpreter running it: without it every Home Assistant class is `Any`, so
subclassing an entity and decorating with `@callback` are reported and the
real checks are skipped. Run it from the venv that has the harness.
`[tool.mypy]` is Home Assistant core's own generated `[mypy]` block for
2026.8.3 plus `strict`, so `warn_unreachable` and core's `enable_error_code`
list apply: a new method that overrides a base method needs
`@typing.override`, under the existing `@property` or `@callback`.
`.github/workflows/tests.yml` runs all four steps on every push with Home
Assistant 2026.8 on Python 3.14, with `pytest-cov` reporting coverage for
`tests/ha`.

`tools/validate_local.py` is the offline stand-in for hassfest and the
cross-file checks nothing else does: `services.yaml` and the README
against the action names in `const.py`, every translated exception key
against `strings.json`, `strings.json` against `translations/en.json`,
the manifest against the components the code imports,
`quality_scale.yaml` against the pinned list of 54 rules, the four
`brand/` PNGs against their sizes, and the `hacs.json` Home Assistant floor
against 2026.3.0. Two checks are there because the obvious form of each is
wrong:

| Check | Why it is written that way |
|---|---|
| `hacs.json` floor compared as parsed integers | As strings `"2026.10.0"` sorts below `"2026.3.0"`, so a text comparison rejects a raised floor. |
| `documentation` and `issue_tracker` hosts rejected when non-routable | A non-routable host answers on one network only, so the URL works where it was written and nowhere a user follows it. A private or link-local address, `localhost`, a `.local`, `.lan` or `.internal` suffix, or a name with no dot fails the run rather than printing a note. |

Logos are pinned to 512x256 and 1024x512 rather than to the
home-assistant/brands shortest-side range, which accepts a pair at a
different aspect from the sibling integrations. Run the validator before a
push.

## hassfest and HACS validation locally

`hassfest` (Home Assistant's manifest/structure validator) lives in
`home-assistant/core`'s `script/hassfest/`, not in the `homeassistant` PyPI
package. A local run needs core checked out at the tag matching the installed
`homeassistant` version: hassfest tracks core's tip, and a skewed pair fails
inside hassfest's own `model.py`.

```bash
git clone --filter=blob:none --sparse --depth 1 --branch 2026.8.3 https://github.com/home-assistant/core.git ha-core-sparse
cd ha-core-sparse
git sparse-checkout set --skip-checks script homeassistant
python -m script.hassfest --action validate --integration-path /path/to/custom_components/envisalink_field_programmer
```

`--filter=blob:none --sparse` fetches hassfest's source without a full
checkout of about 1 GB. `--branch` takes the tag, so the shallow clone lands
on it directly. The `homeassistant` package comes in whole: `script/hassfest`
imports `homeassistant.const`, which imports `homeassistant.generated`, so a
narrower checkout raises `ModuleNotFoundError` before any validator runs.

Core 2026.8.3 sets `required-version = ">=0.16.0"` in its own `[tool.ruff]`,
and hassfest's `serializer.py` resolves `ruff` with `shutil.which` and runs it
with the core checkout as the working directory. The pinned 0.15.21 exits 2
there and hassfest raises `CalledProcessError`, so a 0.16.0 or newer ruff has
to come first on `PATH` for the local run.

`.github/workflows/ci.yml`'s `validate-*` jobs run the version-matched
`home-assistant/actions/hassfest` and `hacs/action` on a push to `main`, on a
`v*` tag and on a pull request. The manifest, `services.yaml`, `strings.json`
and `hacs.json` checks in `tools/validate_local.py` approximate hassfest's and
`hacs/action`'s rules offline.

## The programming form (no frontend build)

There is no JavaScript in this repository and no build step. The guided
programming fields are entities on the panel device, where every other
integration puts its settings, so nothing has to be added to a dashboard.

The form lives in three places:

| File | What it holds |
|---|---|
| `field_programming.py` | `ProgrammingForm`, the values, and `ProgrammingResult`, the outcome of the last press. Both hang off the coordinator, so every entity of an entry reads and writes the same object. |
| `number.py`, `select.py`, `switch.py` | The fields. Setting one writes to the form and calls `async_write_ha_state()`. None of them touches the panel. |
| `button.py` | The only thing that sends. It checks the confirm switch and the required values, calls the matching `async_program_*` coroutine in `field_programming_services.py`, the same one the action calls, records the result, clears the confirmations, and calls `coordinator.async_update_listeners()` so the switches and the result sensor redraw. |

Adding a field means: the attribute on `ProgrammingForm`, the entity in its
platform, the name (and any option names) in `strings.json`, an icon in
`icons.json`, and the read in the button. `tools/validate_local.py` fails a
name or icon that matches no entity, and an entity whose name is not declared.

## Only one TPI client at a time

Observed 2026-07-04 against a live Envisalink EVL-4 and VISTA-21iP: setting
this integration up while `envisalink_new`, or anything else, already holds a
TPI connection to the same module fails with "Could not connect to the
Envisalink at that host/port". The config flow cannot tell that apart from a
wrong host or port. The module's TPI server accepts exactly one client
connection on port 4025 and refuses a second outright, which matches the TPI
spec's "will only accept one client connection on that port".

Before assuming the new entry's host, port or password is wrong: if another
Envisalink integration is configured on the same Home Assistant instance,
check its `disabled_by` in `.storage/core.config_entries`, or in the UI. An
entry that is not disabled is the likely cause.

## The TPI wire format and where it was read from

The protocol this integration speaks is in `client.py`'s module docstring.
Two sources establish it, both read on 2026-07-04 against a live EVL-4 and a
VISTA-21iP.

| Source | What it gave |
|---|---|
| **Raw socket capture** | The EVL sends `Login:\r\n`, takes the plain-text password with no framing and no checksum, and answers `OK\r\n`, `FAILED\r\n` or `Timed Out!\r\n`. Every later message is `%CODE,DATA$` (EVL to client) or `^CODE,DATA$` (client to EVL), terminated by `$`. Keystrokes go one character per frame, `^03,<partition>,<char>$`. |
| **`pyenvisalink`** | The icon-LED bitfield layout, CID event parsing, zone timer dump maths, and the Honeywell response-code table where `01` is "Receive Buffer Overrun". |

The "EnvisaLink TPI Programmer's Document v1.08" (2017-02-10) PDF describes a
different variant of TPI: hex-ASCII, checksum-framed, 3-digit numeric command
codes, a `005`/`505` login handshake. This hardware does not answer it. A
client built to that PDF fails at the handshake with a checksum mismatch on
the literal string `Login:`.

The EVL processes one command at a time. It acknowledges every command with
`^CODE,<response>$` and answers `01` to a command that arrives while the
previous one is still being processed. `EnvisalinkClient._send()` therefore
serializes the full round trip: write, await ack, retry with backoff on
buffer overrun, raise `TPICommandError` on rejection or timeout, and
terminate outbound frames with `\r\n` after the `$` as `pyenvisalink` does.
Firing keystroke frames back to back without ack handling gets only the first
keypress of a multi-keystroke sequence onto the panel, silently. Single-frame
commands such as the poll and the zone timer dump still work, so the symptom
is arm, disarm and bypass doing nothing while status and zones are fine.

`pyenvisalink` is GPL v3. Copies of `envisalink_base_client.py`,
`honeywell_client.py` and `honeywell_envisalinkdefs.py` were downloaded from
`https://github.com/ufodone/envisalink_new` to read those field layouts, then
deleted rather than committed, the same handling as the Vista Programming
Guide PDF. Every module here paraphrases the protocol's meaning in its own
words and carries no copied `pyenvisalink` source.

The Vista `*56`/`*57`/`*99` field-programming keystroke language
(`field_programming.py`, and `programming.py`'s Program Mode guard) is
independent of all of this. It is a string of keystrokes typed at a keypad,
whatever frames carry them.

## Where the Vista programming-guide research came from

The field-programming data model (`field_programming.py`) is built from the
ADEMCO VISTA-21iP/VISTA-21iPSIA Programming Guide, K14488PRV3 10/12 Rev B,
fetched from
`https://advancedsecurityllc.com/wp-content/uploads/2024/05/Honeywell-Vista-21ip-Programming-Guide.pdf`.
That is a mirror; several alarm-dealer sites carry the same Honeywell PDF, so
search "Vista-21ip Programming Guide K14488PRV3" if the link goes dead. The
PDF has an owner-password restriction, so `pypdf` needs `cryptography`
(`pip install pypdf cryptography`) for its AES handling:

```python
from pypdf import PdfReader

r = PdfReader("vista21ip_programming_guide.pdf")
text = "\n".join(page.extract_text() for page in r.pages)
```

The PDF and the extracted text are Honeywell's copyrighted material and are
not committed. `field_programming.py` paraphrases the field meanings in its
own words rather than quoting the manual, and cites the document name and
revision in its module docstring, so the source can be re-fetched and
cross-checked when the field model is in doubt.

The EyezOn/Envisalink brand colours used by the images in `brand/` were read
out of `https://www.eyezon.com/assets/css/main.min.css`, grepping the
`--*-accent-*` custom properties for their hex values.

## Adding or promoting a panel model

Panel support lives in `custom_components/envisalink_field_programmer/panels/`:

| File | What it holds |
|---|---|
| `base.py` | The `PanelDialect` protocol, the `PanelModel` dataclass, and the `Verification` enum (`VERIFIED` / `GRAMMAR_VERIFIED` / `PROVISIONAL`). |
| `vista.py`, `dsc.py` | One dialect per family plus that family's model registry. A dialect is data plus a few small methods: program-mode wrapper, zone-type table, and `opens_program_mode()` for the safety guard. |
| `__init__.py` | The combined registry and the `get_model()` / `get_dialect()` lookups: canonical id, aliases, and punctuation-insensitive matching. |

To add a model within an existing family, append a `PanelModel` to that
family's registry with an honest `verification` level and `notes`. To promote
a model from Provisional/Grammar-verified to Verified, check its field numbers
and zone-type codes against that panel's own programming guide, by the method
the previous section describes, correct anything the family default gets
wrong, and only then bump its `verification`.

Two safety invariants the tests enforce (`tests/ha/test_panels.py`), keep them:

- Only genuinely-verified models carry `Verification.VERIFIED`. The guided
  services refuse anything less without an explicit `confirm_unverified_model`.
- The keystroke guard is family-aware: each dialect's `opens_program_mode()`
  must match that family's real installer-mode trigger (VISTA `<code>800`, DSC
  `*8<code>`) and not the other family's, so the guard can't be bypassed by
  selecting the wrong dialect. Prefer an over-cautious false positive to a miss.

## Guided-programming capabilities per dialect

Guided programming is expressed per operation, not as one on/off switch. A
dialect declares `supported_guided_ops: frozenset[GuidedOp]` (subset of
`ZONE`, `TIMING`, `FUNCTION_KEY`), and each service refuses an operation the
dialect doesn't list:

- Residential VISTA supports all three (`*56` zones, `*34`-style timing,
  `*57` function keys).
- Commercial VISTA (`CommercialVistaDialect`, `dialect_id="vista_commercial"`
  on the 128BP/250BP) supports TIMING only: `<code>8000` entry and the
  partition-specific `*09`-`*12` fields. Its `#93` zone menu is deeply
  conditional and is deliberately not driven without hardware.
- DSC supports none yet: the section keystroke builders
  (`build_dsc_zone_definitions`, `build_dsc_partition_timing`) are pure,
  unit-tested functions, but the client transport is Honeywell-TPI-only, so
  there's no path to send them. Wiring DSC needs a DSC transport handler + a DSC
  fake server, then real-hardware verification before flipping on any GuidedOp.

A model normally uses its family's dialect; set `PanelModel.dialect_id` to point
at a different one (as the commercial VISTA models do). Timing is dialect-owned:
`timing_fields()` lists the valid field ids and `build_timing_keystrokes(field,
value, partition)` does the translation + range validation, so the
`set_system_timing` service stays panel-agnostic.
