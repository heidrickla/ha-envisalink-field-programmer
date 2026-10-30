"""The config flow: setup, every error and the recovery from it, reauth, options.

Against a fake TPI server, so the real login handshake is exercised rather
than a mocked connection.
"""

from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType, section
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.envisalink_field_programmer.client import EnvisalinkClient
from custom_components.envisalink_field_programmer.config_flow import (
    VistaConsoleConfigFlow,
)
from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import PASSWORD, entry_data, setup_entry, unload_entry

# The address an Envisalink has moved away from. RFC 5737 reserves 192.0.2.0/24
# for documentation, so nothing on any network answers there. A name such as
# "localhost" would not do: it resolves to ::1 first on the CI runner, and the
# test harness only permits connections to 127.0.0.1.
OLD_ADDRESS = "192.0.2.10"


def _connection_input(
    fake_server, *, host: str = "127.0.0.1", password: str = PASSWORD, port=None
) -> dict:
    """What a user types on the first screen; the port sits in the collapsed section."""
    return {
        "host": host,
        "password": password,
        "advanced": {"port": fake_server.port if port is None else port},
    }


async def _start(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    return result


async def _to_panel(hass, fake_server, **typed):
    """The first screen submitted with a login the fake server accepts."""
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server, **typed)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "panel"
    return result


async def _finish_and_unload(hass, result) -> None:
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await unload_entry(hass, entry)


def _marker(schema, key):
    for marker in schema.schema:
        if marker == key:
            return marker
    pytest.fail(f"no {key} field on the form")


def _suggested(result, key, within: str | None = None):
    schema = result["data_schema"]
    if within is not None:
        schema = schema.schema[_marker(schema, within)].schema
    return (_marker(schema, key).description or {}).get("suggested_value")


def _advanced(result) -> section:
    schema = result["data_schema"]
    return schema.schema[_marker(schema, "advanced")]


async def test_the_first_screen_asks_only_for_the_address_and_password(
    hass, fake_server
):
    result = await _start(hass)
    assert [str(m) for m in result["data_schema"].schema] == [
        "host",
        "password",
        "advanced",
    ]
    advanced = _advanced(result)
    assert advanced.options["collapsed"] is True
    assert [str(m) for m in advanced.schema.schema] == ["port"]
    assert _marker(advanced.schema, "port").default() == 4025


async def test_user_flow_creates_the_entry(hass, fake_server):
    result = await _to_panel(hass, fake_server)
    assert result["description_placeholders"] == {"host": "127.0.0.1"}
    defaults = {str(m): m.default() for m in result["data_schema"].schema}
    assert defaults == {
        "panel_model": "vista_21ip",
        "num_partitions": 1,
        "num_zones": 8,
        "user_code": "",
        "installer_code": "",
    }
    # The defaults are the answer: Submit alone finishes the setup.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "host": "127.0.0.1",
        "port": fake_server.port,
        "password": PASSWORD,
        "panel_model": "vista_21ip",
        "num_partitions": 1,
        "num_zones": 8,
    }
    assert result["options"] == {"user_code": "", "installer_code": ""}
    assert result["result"].unique_id == f"127.0.0.1:{fake_server.port}"
    await _finish_and_unload(hass, result)


async def test_the_last_step_stores_the_panel_and_both_codes(hass, fake_server):
    result = await _to_panel(hass, fake_server)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "panel_model": "vista_20p",
            "num_partitions": 2,
            "num_zones": 16,
            "user_code": "1357",
            "installer_code": "4112",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["panel_model"] == "vista_20p"
    assert result["data"]["num_partitions"] == 2
    assert result["data"]["num_zones"] == 16
    assert "user_code" not in result["data"]
    assert result["options"] == {"user_code": "1357", "installer_code": "4112"}
    await _finish_and_unload(hass, result)


async def test_wrong_password_then_the_right_one(hass, fake_server):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server, password="wrong")
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
    # The typed password never comes back as a suggested value; the address
    # does, and the error opens the section so the port can be checked.
    assert _suggested(result, "password") is None
    assert _suggested(result, "host") == "127.0.0.1"
    assert _suggested(result, "port", within="advanced") == fake_server.port
    assert _advanced(result).options["collapsed"] is False

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server)
    )
    assert result["step_id"] == "panel"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _finish_and_unload(hass, result)


async def test_unreachable_host_then_the_right_one(hass, fake_server):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server, port=1)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert _suggested(result, "port", within="advanced") == 1

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server)
    )
    assert result["step_id"] == "panel"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _finish_and_unload(hass, result)


async def test_unexpected_error_then_success(hass, fake_server, monkeypatch):
    async def _boom(*_args):
        raise RuntimeError("something else entirely")

    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.config_flow._test_connection",
        _boom,
    )
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server)
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}

    monkeypatch.undo()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server)
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _finish_and_unload(hass, result)


async def _other_client(fake_server) -> EnvisalinkClient:
    """Another TPI client, logged in and holding the module's one session."""
    fake_server.single_session = True
    other = EnvisalinkClient(
        "127.0.0.1", fake_server.port, PASSWORD, event_callback=lambda _event: None
    )
    await other.connect()
    return other


async def test_a_held_session_is_a_step_that_checks_again(hass, fake_server):
    other = await _other_client(fake_server)
    try:
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _connection_input(fake_server)
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "session_busy"
        assert result["errors"] == {}
        assert result["description_placeholders"] == {"host": "127.0.0.1"}

        # Still held: the step stays, now saying so.
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "session_busy"
        assert result["errors"] == {"base": "still_busy"}
    finally:
        await other.disconnect()

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "panel"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["data"]["password"] == PASSWORD
    await _finish_and_unload(hass, result)


async def test_a_wrong_password_found_by_the_busy_check_goes_back_to_the_form(
    hass, fake_server
):
    # A held session drops the login before the password is judged, so a
    # wrong one shows only once the other client has gone.
    other = await _other_client(fake_server)
    try:
        result = await _start(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _connection_input(fake_server, password="wrong")
        )
        assert result["step_id"] == "session_busy"
    finally:
        await other.disconnect()

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}
    assert _suggested(result, "host") == "127.0.0.1"
    assert _suggested(result, "password") is None
    hass.config_entries.flow.async_abort(result["flow_id"])


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("num_zones", 200, "too_many_zones"),
        ("num_partitions", 8, "too_many_partitions"),
    ],
)
async def test_capacity_over_the_model_limit_then_within_it(
    hass, fake_server, field, value, error
):
    # The VISTA-21iP takes 48 zones and 2 partitions.
    result = await _to_panel(hass, fake_server)
    connections = fake_server.connections
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {field: value, "user_code": "1357"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "panel"
    assert result["errors"] == {field: error}
    assert _suggested(result, field) == value
    assert _suggested(result, "user_code") is None
    # The panel step dials nothing.
    assert fake_server.connections == connections

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _finish_and_unload(hass, result)


async def test_same_host_and_port_is_refused(hass, fake_server):
    MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server)).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server)
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_same_unique_id_under_another_name_is_refused(hass, fake_server):
    # The existing entry reached the Envisalink by name; the new attempt by
    # address. The host:port unique id still catches it, after the login.
    MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"127.0.0.1:{fake_server.port}",
        data=entry_data(fake_server, host="envisalink.example.com"),
    ).add_to_hass(hass)
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _connection_input(fake_server)
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


async def test_dhcp_discovery_asks_only_for_the_password_and_keeps_the_mac(
    hass, fake_server
):
    result = await _start_dhcp(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    # The address found is in the collapsed section; only the password is asked.
    assert [str(m) for m in result["data_schema"].schema] == ["password", "advanced"]
    advanced = _advanced(result)
    assert advanced.options["collapsed"] is True
    assert _marker(advanced.schema, "host").default() == "127.0.0.1"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"password": PASSWORD, "advanced": {"port": fake_server.port}},
    )
    assert result["step_id"] == "panel"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "127.0.0.1"
    # The MAC is stored so a later lease elsewhere is known to be this unit.
    assert result["data"]["mac"] == MAC
    await _finish_and_unload(hass, result)


async def test_dhcp_discovery_keeps_the_address_after_an_error(hass, fake_server):
    result = await _start_dhcp(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"password": "wrong", "advanced": {"port": fake_server.port}},
    )
    assert result["errors"] == {"base": "invalid_auth"}
    assert _advanced(result).options["collapsed"] is False
    assert _suggested(result, "host", within="advanced") == "127.0.0.1"
    assert _suggested(result, "password") is None
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_dhcp_at_a_new_address_moves_the_entry_it_belongs_to(hass, fake_server):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"192.0.2.5:{fake_server.port}",
        data=entry_data(fake_server, host="192.0.2.5", mac=MAC),
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


async def test_dhcp_at_a_known_address_learns_the_mac_of_a_handmade_entry(
    hass, fake_server
):
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
    values = entry_data(fake_server, **overrides)
    values.pop("user_code", None)
    return values


def _unique_id_suffixes(hass, entry) -> set[str]:
    """The part of each registered unique id that names the entity."""
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    return {
        registry_entry.unique_id.removeprefix(prefix)
        for registry_entry in er.async_entries_for_config_entry(
            registry, entry.entry_id
        )
    }


async def test_reconfigure_lowering_the_counts_removes_the_orphaned_entities(
    hass, fake_server
):
    # An entity that is simply no longer added keeps its registry entry and
    # shows as unavailable forever, so setup deletes the ones above the counts.
    entry = await setup_entry(hass, fake_server, num_partitions=2, num_zones=8)
    before = _unique_id_suffixes(hass, entry)
    assert {"zone_8", "zone_8_bypass", "partition_2", "partition_2_last_user"} <= before

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _reconfigure_input(fake_server, num_zones=4, num_partitions=1),
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
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS)
    )
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


async def test_reconfigure_rejects_a_wrong_password_then_accepts_the_right_one(
    hass, fake_server
):
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
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS)
    )
    entry.add_to_hass(hass)
    MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server)).add_to_hass(hass)
    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], _reconfigure_input(fake_server, host="127.0.0.1")
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert entry.data["host"] == OLD_ADDRESS


async def test_reconfigure_of_a_loaded_entry_borrows_its_session_to_probe(
    hass, fake_server
):
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


async def test_a_failed_probe_hands_the_session_back_to_the_coordinator(
    hass, fake_server
):
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


async def test_reconfigure_submitted_unchanged_still_gets_its_session_back(
    hass, fake_server
):
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


async def test_reconfigure_that_changes_no_connection_setting_does_not_probe(
    hass, fake_server
):
    # Nothing a login could prove has changed, so taking the module's single
    # session away to test it would cost an outage and prove nothing.
    entry = await setup_entry(hass, fake_server, num_zones=8)
    connections_before = fake_server.connections

    # The password field is left blank, which is what the form offers: it is
    # never suggested back, so a user changing only a zone count submits it
    # empty and the entry keeps the password it has.
    submitted = _reconfigure_input(fake_server, num_zones=4, password="")
    assert VistaConsoleConfigFlow._connection_changed(entry, submitted) is False

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], submitted
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["num_zones"] == 4
    assert entry.data["password"] == PASSWORD
    await hass.async_block_till_done()
    # One new connection, the reload's own. A probe would have made two.
    assert fake_server.connections == connections_before + 1
    await unload_entry(hass, entry)


async def test_reconfigure_that_moves_the_address_or_the_password_does_probe(
    hass, fake_server
):
    # The other side of the same rule: anything a login could prove is worth
    # the outage, so the probe runs.
    entry = await setup_entry(hass, fake_server)
    moved_host = _reconfigure_input(fake_server, host="192.0.2.9", password="")
    moved_port = _reconfigure_input(fake_server, port=fake_server.port + 1, password="")
    new_password = _reconfigure_input(fake_server, password="other")
    assert VistaConsoleConfigFlow._connection_changed(entry, moved_host) is True
    assert VistaConsoleConfigFlow._connection_changed(entry, moved_port) is True
    assert VistaConsoleConfigFlow._connection_changed(entry, new_password) is True
    await unload_entry(hass, entry)


async def test_reconfigure_of_an_unloaded_entry_still_probes(hass, fake_server):
    # Nothing holds the session, so there is nobody to borrow it from and the
    # probe runs exactly as it always did.
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS)
    )
    entry.add_to_hass(hass)
    assert entry.state is config_entries.ConfigEntryState.NOT_LOADED

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _reconfigure_input(fake_server, host="127.0.0.1", password="wrong"),
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["host"] == OLD_ADDRESS

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        _reconfigure_input(fake_server, host="127.0.0.1", password=PASSWORD),
    )
    assert result["type"] is FlowResultType.ABORT
    assert entry.data["host"] == "127.0.0.1"
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_reconfigure_names_a_session_another_client_holds(hass, fake_server):
    # The entry is not loaded, so the session the probe meets is someone else's.
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(fake_server, host=OLD_ADDRESS)
    )
    entry.add_to_hass(hass)
    other = await _other_client(fake_server)
    try:
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], _reconfigure_input(fake_server, host="127.0.0.1")
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "session_busy"}
        assert entry.data["host"] == OLD_ADDRESS
    finally:
        await other.disconnect()
    hass.config_entries.flow.async_abort(result["flow_id"])


async def test_reauth_with_a_still_wrong_password_then_the_right_one(hass, fake_server):
    entry = MockConfigEntry(
        domain=DOMAIN, data=entry_data(fake_server, password="stale")
    )
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
    # Zone doubling nobody answered is saved as not stated, never as off.
    assert entry.options == {
        "user_code": "1234",
        "installer_code": "4112",
        "keepalive_interval": 45,
        "zone_doubling": "not_stated",
    }
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_options_state_zone_doubling_on_a_model_that_has_it(hass, fake_server):
    entry = await setup_entry(hass, fake_server, options={"installer_code": "4112"})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    marker = next(m for m in result["data_schema"].schema if m == "zone_doubling")
    assert marker.default() == "not_stated"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keepalive_interval": 30, "zone_doubling": "on"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["zone_doubling"] == "on"
    await hass.async_block_till_done()

    # The stored answer is the form's default next time.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    marker = next(m for m in result["data_schema"].schema if m == "zone_doubling")
    assert marker.default() == "on"
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"keepalive_interval": 30}
    )
    assert entry.options["zone_doubling"] == "on"
    await hass.async_block_till_done()
    await unload_entry(hass, entry)


async def test_options_do_not_offer_zone_doubling_where_the_model_lacks_it(
    hass, fake_server
):
    entry = await setup_entry(
        hass, fake_server, panel_model="vista_15p", options={"installer_code": "4112"}
    )
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert "zone_doubling" not in result["data_schema"].schema
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"keepalive_interval": 30}
    )
    assert "zone_doubling" not in entry.options
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
