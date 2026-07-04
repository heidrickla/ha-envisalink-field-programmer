# Development environment notes

How this repo's dev/test environment was actually built, and how to
recreate it from scratch on a fresh machine (or debug it when something
about the test setup itself seems broken, as opposed to the integration
code). Written from a Windows dev box; adjust activation commands if
you're on Linux/Mac.

## Python version: use 3.12, not 3.13

```bash
py install 3.12          # if not already installed
py -3.12 -m venv .venv
source .venv/Scripts/activate   # .venv/bin/activate on Linux/Mac
pip install pytest pytest-asyncio pytest-homeassistant-custom-component ruff
```

**Why 3.12 and not the newer 3.13**: `homeassistant` pins `lru-dict==1.3.0`
exactly. That version has no prebuilt wheel for `cp313` on Windows, so pip
falls back to compiling it from source, which needs the MSVC C++ Build
Tools (not installed, and not worth installing just for this). `lru-dict`
1.3.0 *does* have a `cp312-win_amd64` wheel, so Python 3.12 sidesteps the
problem entirely. If a future `homeassistant` release bumps its `lru-dict`
pin to something with a `cp313` wheel, 3.13 should work fine too -- check
`pip show homeassistant | grep -i lru` if you want to retry it.

## Why `tests/conftest.py` does two unusual things

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

## Running tests and lint

```bash
pytest tests/ -v            # 62 tests as of this writing, ~8s
ruff check custom_components tests
```

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
`main` is version-skewed against the `homeassistant` 2025.1.4 package this
venv has installed (pinned by `pytest-homeassistant-custom-component`), and
depends on newer language/stdlib behavior not worth chasing for a one-off
local check. Manifest/services.yaml/strings.json were instead reviewed by
hand against hassfest's known rules (see the CI workflow's `validate-*`
jobs, which run the *actual, version-matched* `home-assistant/actions/hassfest`
and `hacs/action` GitHub Actions on every push -- that's the real
authoritative check, not a local approximation). If you want to re-attempt
a local run, you'd need to either check out core at a tag matching the
installed `homeassistant` version, or bump the venv's `homeassistant`
pinned version to something closer to current `main`.

## Frontend card build

```bash
cd www/envisalink-field-programmer-card
npm install
npm run build          # writes ../../custom_components/envisalink_field_programmer/www/envisalink-field-programmer-card.js
npx tsc --noEmit        # type-check only, no output
```

Note the build output path: it deliberately writes into
`custom_components/envisalink_field_programmer/www/`, not a local `dist/` folder --  see
`frontend.py`'s docstring for why (HACS only ships the
`custom_components/<domain>` tree).

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

The EyezOn/Envisalink brand color research (for the Lovelace card's accent
colors) came from fetching `https://www.eyezon.com/assets/css/main.min.css`
directly and grepping for `--*-accent-*` custom properties and their hex
values, rather than trusting a generic web search (which turned up nothing
useful) or visual inspection (`WebFetch` strips CSS from rendered pages).
