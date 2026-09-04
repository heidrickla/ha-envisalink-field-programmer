"""Shared test fixtures.

pytest-homeassistant-custom-component looks for custom integrations under
its own bundled ``testing_config/custom_components`` directory (see
``pytest_homeassistant_custom_component.common.get_test_config_dir``), not
under this repo's ``custom_components/``. We mirror our integration into
that directory before the test session starts so ``enable_custom_integrations``
can discover it as ``envisalink_field_programmer``, same as it would in a
real HA config dir.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import pytest_socket

pytest_plugins = "pytest_homeassistant_custom_component"

REPO_ROOT = Path(__file__).parent.parent
SOURCE = REPO_ROOT / "custom_components" / "envisalink_field_programmer"


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


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


# pytest-homeassistant-custom-component calls
# ``pytest_socket.disable_socket(allow_unix_socket=True)`` before every test.
# On Windows, asyncio's ProactorEventLoop needs a real AF_INET socketpair
# just to construct its self-pipe -- unix sockets don't cover it -- so event
# loop creation itself fails before any test code runs. Our TPI client tests
# also open real loopback TCP connections against an in-process fake
# Envisalink server, which the same guard would block. Neutering
# disable_socket() (rather than trying to win a hook-ordering race against
# it) is the reliable fix: it must happen before the harness's own
# pytest_runtest_setup call, and module import time is the earliest and only
# deterministic point for that.
pytest_socket.disable_socket = lambda *args, **kwargs: None
