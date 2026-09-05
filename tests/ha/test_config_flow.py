"""The config flow: setup, every error and the recovery from it, reauth, options.

Against a fake TPI server, so the real login handshake is exercised rather
than a mocked connection.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import PASSWORD, entry_data, setup_entry, unload_entry

# The address an Envisalink has moved away from. RFC 5737 reserves 192.0.2.0/24
# for documentation, so nothing on any network answers there. A name such as
# "localhost" would not do: it resolves to ::1 first on the CI runner, and the
# test harness only permits connections to 127.0.0.1.
OLD_ADDRESS = "192.0.2.10"


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


MAC = "00:1c:2a:aa:bb:cc"


def _dhcp(host: str = "127.0.0.1") -> DhcpServiceInfo:
    """A DHCP lease from a device with the Envisacor MAC prefix."""
    return DhcpServiceInfo(ip=host, hostname="envisalink", macaddress="001c2aaabbcc")


async def _start_dhcp(hass, host: str = "127.0.0.1"):
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=_dhcp(host)
    )


async def test_dhcp_discovery_prefills_the_address_and_keeps_the_mac(hass, fake_server):
    result = await _start_dhcp(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # The address is offered; the password still has to be typed.
    assert _suggested(result, "host") == "127.0.0.1"
    assert _suggested(result, "password") is None

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _form_input(fake_server)
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The MAC is stored so a later lease elsewhere is known to be this unit.
    assert result["data"]["mac"] == MAC
    await _finish_and_unload(hass, result)


async def test_dhcp_at_a_new_address_moves_the_entry_it_belongs_to(hass, fake_server):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"10.0.0.5:{fake_server.port}",
        data=entry_data(fake_server, host="10.0.0.5", mac=MAC),
    )
    entry.add_to_hass(hass)

    result = await _start_dhcp(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == "127.0.0.1"
    assert entry.unique_id == f"127.0.0.1:{fake_server.port}"
    assert entry.title == "Envisalink Field Programmer (127.0.0.1)"
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_dhcp_at_a_known_address_learns_the_mac_of_a_handmade_entry(hass, fake_server):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server))
    entry.add_to_hass(hass)
    assert "mac" not in entry.data

    result = await _start_dhcp(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["mac"] == MAC


async def test_dhcp_for_an_already_discovered_address_aborts(hass, fake_server):
    # An entry made from an earlier discovery of some other Envisalink that
    # now has this address: the unique id catches it.
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="127.0.0.1:4025",
        data=entry_data(fake_server, port=4025, mac="00:1c:2a:11:22:33"),
    ).add_to_hass(hass)
    result = await _start_dhcp(hass)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


def _reconfigure_input(fake_server, **overrides) -> dict:
    """What a user submits on the reconfigure form (no codes there)."""
    values = _form_input(fake_server, **overrides)
    values.pop("user_code", None)
    values["panel_model"] = overrides.get("panel_model", "vista_21ip")
    return values


def _unique_id_suffixes(hass, entry) -> set[str]:
    """The part of each registered unique id that names the entity."""
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    return {
        registry_entry.unique_id.removeprefix(prefix)
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def test_reconfigure_lowering_the_counts_removes_the_orphaned_entities(hass, fake_server):
    # An entity that is simply no longer added keeps its registry entry and
    # shows as unavailable forever, so setup deletes the ones above the counts.
    entry = await setup_entry(hass, fake_server, num_partitions=2, num_zones=8)
    before = _unique_id_suffixes(hass, entry)
    assert {"zone_8", "zone_8_bypass", "partition_2", "partition_2_last_user"} <= before

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, num_zones=4, num_partitions=1)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    after = _unique_id_suffixes(hass, entry)
    orphans = {
        suffix
        for suffix in after
        if suffix.startswith(("zone_5", "zone_6", "zone_7", "zone_8", "partition_2"))
    }
    assert orphans == set()
    assert {"zone_4", "zone_4_bypass", "partition_1", "partition_1_last_user"} <= after
    # The entities that carry no number are left alone.
    assert {"last_event", "system_trouble"} <= after
    await unload_entry(hass, entry)


async def test_reconfigure_moves_the_entry_to_a_new_address(hass, fake_server):
    # The Envisalink was given a new address. The unique id is the address, so
    # it moves with the entry. The entry is added without being set up because
    # that is the state a moved unit leaves it in: nothing answers at the old
    # address, so the entry has no update listener and the flow reloads it.
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS))
    entry.add_to_hass(hass)
    assert entry.unique_id is None
    result = await entry.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    # The stored password is not offered back to the browser.
    assert _suggested(result, "password") is None
    assert _suggested(result, "host") == OLD_ADDRESS

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, host="127.0.0.1")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["host"] == "127.0.0.1"
    assert entry.unique_id == f"127.0.0.1:{fake_server.port}"
    assert entry.title == "Envisalink Field Programmer (127.0.0.1)"
    # Blank password field: the stored one is kept.
    assert entry.data["password"] == PASSWORD
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_reconfigure_stores_a_new_password(hass, fake_server):
    entry = await setup_entry(hass, fake_server)
    result = await entry.start_reconfigure_flow(hass)
    fake_server.password = "fresh"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, password="fresh")
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["password"] == "fresh"
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_reconfigure_rejects_a_wrong_password_then_accepts_the_right_one(hass, fake_server):
    entry = await setup_entry(hass, fake_server)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, password="wrong")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, num_zones=12)
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["num_zones"] == 12
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_reconfigure_refuses_counts_over_the_model_limit(hass, fake_server):
    entry = await setup_entry(hass, fake_server)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, num_zones=200)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"num_zones": "too_many_zones"}
    assert entry.data["num_zones"] == 8
    await unload_entry(hass, entry)


async def test_reconfigure_refuses_an_address_another_entry_owns(hass, fake_server):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS))
    entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server)).add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, host="127.0.0.1")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == OLD_ADDRESS


async def test_reconfigure_of_a_loaded_entry_borrows_its_session_to_probe(hass, fake_server):
    # Measured against the hardware on 2026-09-05: the module admits one TPI
    # client, so a probe made while the coordinator holds the session was
    # answered "cannot connect" every time and the form could never be
    # submitted. The coordinator lets go for the probe now.
    fake_server.single_session = True
    entry = await setup_entry(hass, fake_server)
    assert entry.runtime_data.client.connected

    result = await entry.start_reconfigure_flow(hass)
    fake_server.password = "fresh"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, password="fresh")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["password"] == "fresh"
    await hass.async_block_till_done()
    # The reload put the session back.
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.runtime_data.client.connected
    await unload_entry(hass, entry)


async def test_a_failed_probe_hands_the_session_back_to_the_coordinator(hass, fake_server):
    # The entry is staying exactly as it was, so it must not be left
    # disconnected because a reconfigure was abandoned on the error.
    fake_server.single_session = True
    entry = await setup_entry(hass, fake_server)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, password="wrong")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.runtime_data.client.connected
    await unload_entry(hass, entry)


async def test_reconfigure_submitted_unchanged_still_gets_its_session_back(hass, fake_server):
    # The same settings retyped: Home Assistant finds nothing to change, so
    # nothing reloads the entry, and the session the probe borrowed has to be
    # handed back by the flow or the entry sits there disconnected.
    fake_server.single_session = True
    entry = MockConfigEntry(
        domain=DOMAIN,
        data=entry_data(fake_server),
        unique_id=f"127.0.0.1:{fake_server.port}",
        title="Envisalink Field Programmer (127.0.0.1)",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, password=PASSWORD)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.state is config_entries.ConfigEntryState.LOADED
    assert entry.runtime_data.client.connected
    await unload_entry(hass, entry)


async def test_reconfigure_that_changes_no_connection_setting_does_not_probe(hass, fake_server):
    # Nothing a login could prove has changed, so taking the module's single
    # session away to test it would cost an outage and prove nothing.
    entry = await setup_entry(hass, fake_server, num_zones=8)
    connections_before = fake_server.connections

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, num_zones=4)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["num_zones"] == 4
    await hass.async_block_till_done()
    # One new connection, the reload's own. A probe would have made two.
    assert fake_server.connections == connections_before + 1
    await unload_entry(hass, entry)


async def test_reconfigure_of_an_unloaded_entry_still_probes(hass, fake_server):
    # Nothing holds the session, so there is nobody to borrow it from and the
    # probe runs exactly as it always did.
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS))
    entry.add_to_hass(hass)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, host="127.0.0.1", password="wrong")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["host"] == OLD_ADDRESS

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, host="127.0.0.1", password=PASSWORD)
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["host"] == "127.0.0.1"
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


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
