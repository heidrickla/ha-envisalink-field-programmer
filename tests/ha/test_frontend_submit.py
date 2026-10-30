"""Each setup form, submitted the way the dialog sends it.

The data comes from the schema the frontend receives, through a port of its
initial-data code (frontend_form.py); the Address and port section is never
opened, so the fake module listens on the default TPI port.
"""

from __future__ import annotations

import pytest
from homeassistant.data_entry_flow import FlowResultType

from custom_components.envisalink_field_programmer.const import DEFAULT_PORT
from tests.helpers import FakeEnvisalinkServer

from .conftest import PASSWORD
from .frontend_form import frontend_submission
from .test_config_flow import _finish_and_unload, _start, _start_dhcp


@pytest.fixture
async def module():
    """The fake module on the port the collapsed section holds by default."""
    server = FakeEnvisalinkServer(password=PASSWORD)
    await server.start(port=DEFAULT_PORT)
    yield server
    await server.stop()


async def _submit(hass, result, typed=None):
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], frontend_submission(result, typed)
    )


async def test_the_first_screen_submits_with_the_section_collapsed(hass, module):
    result = await _start(hass)
    result = await _submit(hass, result, {"host": "127.0.0.1", "password": PASSWORD})
    assert result["step_id"] == "panel"

    # The panel step finishes on Submit alone.
    result = await _submit(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["port"] == DEFAULT_PORT
    assert result["data"]["panel_model"] == "vista_21ip"
    await _finish_and_unload(hass, result)


async def test_the_first_screen_shown_again_after_an_error_submits(hass, module):
    result = await _start(hass)
    result = await _submit(hass, result, {"host": "127.0.0.1", "password": "wrong"})
    assert result["errors"] == {"base": "invalid_auth"}

    # The address comes back filled in; the password is typed again.
    result = await _submit(hass, result, {"password": PASSWORD})
    assert result["step_id"] == "panel"
    result = await _submit(hass, result)
    await _finish_and_unload(hass, result)


async def test_a_discovered_module_submits_with_the_section_collapsed(hass, module):
    result = await _start_dhcp(hass)
    result = await _submit(hass, result, {"password": PASSWORD})
    assert result["step_id"] == "panel"
    result = await _submit(hass, result)
    assert result["data"]["host"] == "127.0.0.1"
    await _finish_and_unload(hass, result)


async def test_the_busy_step_submits_untouched(hass, module):
    module.drop_logins = 1
    result = await _start(hass)
    result = await _submit(hass, result, {"host": "127.0.0.1", "password": PASSWORD})
    assert result["step_id"] == "session_busy"

    # A form with no fields: core sends its schema as [] and the dialog sends {}.
    assert result["data_schema"] is None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "panel"
    result = await _submit(hass, result)
    await _finish_and_unload(hass, result)


async def test_what_was_typed_in_the_section_comes_back_after_an_error(hass, module):
    result = await _start(hass)
    sent = frontend_submission(result, {"host": "127.0.0.1", "password": PASSWORD})
    sent["advanced"]["port"] = DEFAULT_PORT + 1
    result = await hass.config_entries.flow.async_configure(result["flow_id"], sent)
    assert result["step_id"] == "user"
    assert result["errors"]

    # The section reopens holding the typed port, and Submit sends it back.
    again = frontend_submission(result, {"password": PASSWORD})
    assert again["advanced"]["port"] == DEFAULT_PORT + 1
    hass.config_entries.flow.async_abort(result["flow_id"])
