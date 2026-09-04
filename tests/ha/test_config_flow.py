"""The config flow: setup, every error and the recovery from it, reauth, options.

Against a fake TPI server, so the real login handshake is exercised rather
than a mocked connection.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import PASSWORD, entry_data, setup_entry, unload_entry


def _form_input(fake_server, **overrides) -> dict:
    """What a user types on the setup form."""
    values = entry_data(fake_server, **overrides)
    values.pop("panel_model", None)
    return values


async def _start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def _finish_and_unload(hass, result) -> None:
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await unload_entry(hass, entry)


def _suggested(result, key):
    for marker in result["data_schema"].schema:
        if marker == key:
            return (marker.description or {}).get("suggested_value")
    pytest.fail(f"no {key} field on the form")


async def test_user_flow_creates_the_entry(hass, fake_server):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "127.0.0.1"
    assert result["data"]["panel_model"] == "vista_21ip"
    assert result["result"].unique_id == f"127.0.0.1:{fake_server.port}"
    await _finish_and_unload(hass, result)


async def test_wrong_password_then_the_right_one(hass, fake_server):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server, password="wrong")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    # The typed secrets never come back as suggested values; the address does.
    assert _suggested(result, "password") is None
    assert _suggested(result, "user_code") is None
    assert _suggested(result, "host") == "127.0.0.1"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    await _finish_and_unload(hass, result)


async def test_unreachable_host_then_the_right_one(hass, fake_server):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server, port=1)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    await _finish_and_unload(hass, result)


async def test_unexpected_error_then_success(hass, fake_server, monkeypatch):
    async def _boom(*_args):
        raise RuntimeError("something else entirely")

    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.config_flow._test_connection", _boom
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}

    monkeypatch.undo()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    await _finish_and_unload(hass, result)


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("num_zones", 200, "too_many_zones"),
        ("num_partitions", 8, "too_many_partitions"),
    ],
)
async def test_capacity_over_the_model_limit_then_within_it(hass, fake_server, field, value, error):
    # The VISTA-21iP takes 48 zones and 2 partitions.
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server, **{field: value})
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {field: error}
    # Nothing was tried against the Envisalink.
    assert fake_server.received == []

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    await _finish_and_unload(hass, result)


async def test_same_host_and_port_is_refused(hass, fake_server):
    MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server)).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_same_unique_id_under_another_name_is_refused(hass, fake_server):
    # The existing entry reached the Envisalink by name; the new attempt by
    # address. The host:port unique id still catches it, after the login.
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"127.0.0.1:{fake_server.port}",
        data=entry_data(fake_server, host="envisalink.local"),
    ).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_with_a_still_wrong_password_then_the_right_one(hass, fake_server):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server, password="stale"))
    entry.add_to_hass(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    assert result["description_placeholders"]["host"] == "127.0.0.1"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": "still wrong"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"password": PASSWORD}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == PASSWORD
    assert entry.data["host"] == "127.0.0.1"
    # Reauth reloads the entry, which now connects.
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    await unload_entry(hass, entry)


async def test_options_form_never_shows_the_stored_codes(hass, fake_server):
    entry = await setup_entry(
        hass, fake_server, options={"installer_code": "4112", "user_code": "1234"}
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    for key in ("user_code", "installer_code"):
        marker = next(m for m in result["data_schema"].schema if m == key)
        assert marker.default() == ""
        assert (marker.description or {}).get("suggested_value") in (None, "")
    assert result["description_placeholders"] == {
        "user_code_state": "set",
        "installer_code_state": "set",
    }
    await unload_entry(hass, entry)


async def test_options_blank_codes_keep_the_stored_ones(hass, fake_server):
    entry = await setup_entry(hass, fake_server, options={"installer_code": "4112"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keepalive_interval": 45}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The default user code came from the setup form; the installer code from
    # the earlier options. Both survive an options save that left them blank.
    assert entry.options == {
        "user_code": "1234",
        "installer_code": "4112",
        "keepalive_interval": 45,
    }
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_options_new_codes_replace_and_switches_remove(hass, fake_server):
    entry = await setup_entry(
        hass, fake_server, options={"installer_code": "4112", "user_code": "1234"}
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"installer_code": "5678", "remove_user_code": True, "keepalive_interval": 30},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["installer_code"] == "5678"
    assert entry.options["user_code"] == ""
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["description_placeholders"]["user_code_state"] == "not set"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"remove_installer_code": True, "keepalive_interval": 30}
    )
    assert entry.options["installer_code"] == ""
    await hass.async_block_till_done()
    await unload_entry(hass, entry)
