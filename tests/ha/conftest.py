"""Fixtures for the Home Assistant layer tests.

These need pytest-homeassistant-custom-component and skip as a whole when it
is absent, so the pure protocol tests one level up still run on a bare
checkout. This conftest lives in its own directory on purpose: a conftest
applies to everything at or below it, and the harness's machinery would
otherwise attach to the pure tests too.

Two things here are unusual and both are deliberate:

1. The integration is mirrored into the harness's own
   ``testing_config/custom_components`` directory before the session starts,
   which is where ``enable_custom_integrations`` looks for custom
   integrations (see ``get_test_config_dir``), not this repo's tree.

2. ``pytest_socket.disable_socket`` is neutered at import time. The harness
   calls it before every test. On Windows, asyncio's ProactorEventLoop needs
   a real AF_INET socketpair for its self-pipe, so event loop creation itself
   fails with the guard active. The tests here also open real loopback TCP
   connections against an in-process fake Envisalink server, which the guard
   would block. Module import is the earliest deterministic point before the
   harness's own pytest_runtest_setup runs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

import pytest_socket  # noqa: E402
from pytest_homeassistant_custom_component.common import (  # noqa: E402
    MockConfigEntry,
)

from custom_components.envisalink_field_programmer.const import DOMAIN  # noqa: E402
from tests.helpers import FakeEnvisalinkServer  # noqa: E402

REPO_ROOT = Path(__file__).parent.parent.parent
SOURCE = REPO_ROOT / "custom_components" / "envisalink_field_programmer"

PASSWORD = "user"


def _mirror_into_test_config_dir() -> None:
    import pytest_homeassistant_custom_component.common as ha_test_common

    dest_root = Path(ha_test_common.get_test_config_dir("custom_components"))
    dest = dest_root / "envisalink_field_programmer"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        SOURCE,
        dest,
        ignore=shutil.ignore_patterns("__pycache__", "www"),
    )


_mirror_into_test_config_dir()

pytest_socket.disable_socket = lambda *args, **kwargs: None


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def fake_server():
    """A fake Envisalink speaking the real TPI protocol on a loopback port."""
    server = FakeEnvisalinkServer(password=PASSWORD)
    await server.start()
    yield server
    await server.stop()


def entry_data(fake_server: FakeEnvisalinkServer, **overrides) -> dict:
    """Config entry data pointing at the fake server."""
    data = {
        "host": "127.0.0.1",
        "port": fake_server.port,
        "password": PASSWORD,
        "panel_model": "vista_21ip",
        "user_code": "1234",
        "num_partitions": 1,
        "num_zones": 8,
    }
    data.update(overrides)
    return data


async def setup_entry(
    hass,
    fake_server: FakeEnvisalinkServer,
    *,
    options: dict | None = None,
    **overrides,
) -> MockConfigEntry:
    """Add and set up an entry against the fake server; assert it loaded."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data(fake_server, **overrides),
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def unload_entry(hass, entry: MockConfigEntry) -> None:
    """Unload explicitly so the coordinator's tasks stop before the fake server."""
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
