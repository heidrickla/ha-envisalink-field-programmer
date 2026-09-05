"""Setup and unload against a fake TPI server: entities, pushed events, the
failure modes, the connection-loss logging, the action refusals, diagnostics."""

from __future__ import annotations

import asyncio
import logging

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.envisalink_field_programmer.client import (
    EnvisalinkClient,
    TPICommandError,
    TPIConnectionError,
)
from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.helpers import FakeEnvisalinkServer

from .conftest import entry_data, setup_entry, unload_entry

ACTIONS = (
    "send_keystrokes",
    "toggle_zone_bypass",
    "program_zone",
    "set_system_timing",
    "program_function_key",
)


def _entity_id(hass, entry: MockConfigEntry, domain: str, suffix: str) -> str:
    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_{suffix}"
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"no entity registered for unique_id={unique_id!r}"
    return entity_id


def _reauth_flows(hass) -> list:
    return [
        flow
        for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == SOURCE_REAUTH
    ]


async def test_entities_created_and_default_state(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4)

    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    alarm_state = hass.states.get(alarm_entity_id)
    assert alarm_state is not None
    assert alarm_state.state == "disarmed"

    zone_entity_id = _entity_id(hass, entry, "binary_sensor", "zone_1")
    zone_state = hass.states.get(zone_entity_id)
    assert zone_state is not None
    assert zone_state.state == "off"

    await unload_entry(hass, entry)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_entity_names_come_from_the_translations(hass, fake_server):
    # Names are translation keys now, so a missing entity string shows up as
    # a friendly name that is the object id rather than the text below.
    entry = await setup_entry(hass, fake_server, num_zones=2, num_partitions=1)

    def friendly(domain: str, suffix: str) -> str:
        state = hass.states.get(_entity_id(hass, entry, domain, suffix))
        assert state is not None
        name: str = state.attributes["friendly_name"]
        return name

    assert friendly("alarm_control_panel", "partition_1").endswith("Partition")
    assert friendly("binary_sensor", "zone_2").endswith("Zone 2")
    assert friendly("binary_sensor", "system_trouble").endswith("System Trouble")
    assert friendly("sensor", "partition_1_last_user").endswith("Last User")

    await unload_entry(hass, entry)


async def test_several_partitions_get_numbered_names(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2, num_partitions=2)
    for number in (1, 2):
        alarm = hass.states.get(
            _entity_id(hass, entry, "alarm_control_panel", f"partition_{number}")
        )
        assert alarm is not None
        assert alarm.attributes["friendly_name"].endswith(f"Partition {number}")
        last_user = hass.states.get(
            _entity_id(hass, entry, "sensor", f"partition_{number}_last_user")
        )
        assert last_user is not None
        assert last_user.attributes["friendly_name"].endswith(f"Partition {number} Last User")
    await unload_entry(hass, entry)


async def test_a_named_zone_keeps_the_users_own_text(hass, fake_server):
    entry = await setup_entry(
        hass, fake_server, num_zones=2, options={"zone_names": {"1": "Front Door"}}
    )
    named = hass.states.get(_entity_id(hass, entry, "binary_sensor", "zone_1"))
    assert named is not None
    assert named.attributes["friendly_name"].endswith("Front Door")
    await unload_entry(hass, entry)


async def test_noisy_diagnostics_are_disabled_by_default(hass, fake_server):
    # Last Event changes on every keepalive acknowledgement and the bypass
    # switches write to the panel, so neither is created enabled.
    entry = await setup_entry(hass, fake_server, num_zones=2)
    registry = er.async_get(hass)
    for domain, suffix in (("sensor", "last_event"), ("switch", "zone_1_bypass")):
        entity_id = _entity_id(hass, entry, domain, suffix)
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entity_id) is None
    # The other diagnostic sensor stays enabled.
    assert hass.states.get(_entity_id(hass, entry, "sensor", "partition_1_last_user")) is not None
    await unload_entry(hass, entry)


async def test_arm_event_updates_alarm_entity(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4)
    # Icon LED bits: armed_away (bit 2) + ac_present (bit 3) = 0xC.
    await fake_server.push("00", "1,c,0,00,ARMED AWAY")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()

    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    assert hass.states.get(alarm_entity_id).state == "armed_away"

    await unload_entry(hass, entry)


async def test_zone_open_event_updates_binary_sensor(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4)
    # Zone timer dump, 4 zones: zone 2's chunk (FEFF, little-endian) decodes
    # to 1 tick since last fault -- recently faulted, so considered open.
    hex_string = "0000" + "FEFF" + "0000" + "0000"
    await fake_server.push("FF", hex_string)
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()

    zone_entity_id = _entity_id(hass, entry, "binary_sensor", "zone_2")
    assert hass.states.get(zone_entity_id).state == "on"

    await unload_entry(hass, entry)


async def test_disconnect_marks_entities_unavailable_and_logs_once(hass, fake_server, caplog):
    entry = await setup_entry(hass, fake_server, num_zones=4)
    with caplog.at_level(logging.INFO):
        await fake_server.stop()
        await asyncio.sleep(0.1)
        await hass.async_block_till_done()

    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    assert hass.states.get(alarm_entity_id).state == "unavailable"
    lost = [r for r in caplog.records if "Lost the connection" in r.getMessage()]
    assert len(lost) == 1
    assert lost[0].levelno == logging.INFO

    await unload_entry(hass, entry)


async def test_reconnect_restores_availability_and_logs_once(
    hass, fake_server, caplog, monkeypatch
):
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_BACKOFF_MIN",
        0.05,
    )
    entry = await setup_entry(hass, fake_server, num_zones=4)
    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    port = fake_server.port

    with caplog.at_level(logging.INFO):
        await fake_server.stop()
        await asyncio.sleep(0.1)
        await hass.async_block_till_done()
        assert hass.states.get(alarm_entity_id).state == "unavailable"

        # The Envisalink comes back on the same port.
        replacement = FakeEnvisalinkServer(password="user")
        await replacement.start(port)
        try:
            for _ in range(40):
                await asyncio.sleep(0.05)
                await hass.async_block_till_done()
                if hass.states.get(alarm_entity_id).state != "unavailable":
                    break
            assert hass.states.get(alarm_entity_id).state == "disarmed"
            reconnected = [r for r in caplog.records if "Reconnected" in r.getMessage()]
            assert len(reconnected) == 1
            await unload_entry(hass, entry)
        finally:
            await replacement.stop()


async def test_wrong_password_starts_reauth_instead_of_crashing(hass, fake_server):
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server, password="wrong"))
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    flows = _reauth_flows(hass)
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"


async def test_unreachable_envisalink_is_retried(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "127.0.0.1",
            "port": 1,
            "password": "user",
            "num_partitions": 1,
            "num_zones": 4,
        },
    )
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert _reauth_flows(hass) == []


async def test_a_long_outage_raises_a_repair_issue_and_recovery_clears_it(
    hass, fake_server, monkeypatch
):
    # The Envisalink admits one TPI client, so a held session looks exactly
    # like an unreachable host. After a few failed reconnects the repair
    # issue says so; the reconnection takes it away again.
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_BACKOFF_MIN", 0.02
    )
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_FAILURES_BEFORE_ISSUE",
        2,
    )
    entry = await setup_entry(hass, fake_server, num_zones=4)
    issue_id = f"tpi_session_busy_{entry.entry_id}"
    registry = ir.async_get(hass)
    port = fake_server.port

    # Every reconnection is refused, the way a held TPI session refuses one,
    # until the flag is cleared below.
    real_connect = EnvisalinkClient.connect
    refuse = {"session": True}

    async def _connect(self):
        if refuse["session"]:
            raise TPIConnectionError("another client holds the session")
        await real_connect(self)

    monkeypatch.setattr(EnvisalinkClient, "connect", _connect)
    await fake_server.stop()
    for _ in range(60):
        await asyncio.sleep(0.05)
        await hass.async_block_till_done()
        if registry.async_get_issue(DOMAIN, issue_id) is not None:
            break
    issue = registry.async_get_issue(DOMAIN, issue_id)
    assert issue is not None
    assert issue.translation_key == "tpi_session_busy"
    assert issue.translation_placeholders["host"] == "127.0.0.1"
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable

    replacement = FakeEnvisalinkServer(password="user")
    await replacement.start(port)
    refuse["session"] = False
    try:
        for _ in range(60):
            await asyncio.sleep(0.05)
            await hass.async_block_till_done()
            if registry.async_get_issue(DOMAIN, issue_id) is None:
                break
        assert registry.async_get_issue(DOMAIN, issue_id) is None
        await unload_entry(hass, entry)
    finally:
        await replacement.stop()


async def test_removing_the_entry_takes_its_repair_issue_with_it(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4)
    issue_id = f"tpi_session_busy_{entry.entry_id}"
    entry.runtime_data._async_raise_connection_issue()
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_refused_first_command_is_retried_and_the_socket_released(
    hass, fake_server, monkeypatch
):
    # The login works but the zone timer dump is refused: a retry, not a
    # crash, and the single TPI slot is given back so the retry can log in.
    disconnects: list[bool] = []
    real_disconnect = EnvisalinkClient.disconnect

    async def _dump(self):
        raise TPICommandError("Unknown Command")

    async def _disconnect(self):
        disconnects.append(True)
        await real_disconnect(self)

    monkeypatch.setattr(EnvisalinkClient, "dump_zone_timers", _dump)
    monkeypatch.setattr(EnvisalinkClient, "disconnect", _disconnect)
    entry = MockConfigEntry(domain=DOMAIN, data=entry_data(fake_server, num_zones=4))
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    # Closed by the coordinator (and again by core's on-unload cleanup, which
    # is idempotent), and no reconnect loop was left running for the retry to
    # trip over.
    assert disconnects
    assert not entry._background_tasks


async def test_actions_exist_before_any_entry_and_refuse_an_unknown_one(hass):
    assert await async_setup_component(hass, DOMAIN, {})
    for action in ACTIONS:
        assert hass.services.has_service(DOMAIN, action)
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN,
            "send_keystrokes",
            {"entry_id": "nope", "partition": 1, "keys": "*101#"},
            blocking=True,
        )
    assert raised.value.translation_key == "entry_not_found"


async def test_actions_refuse_an_unloaded_entry(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4)
    await unload_entry(hass, entry)
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN,
            "toggle_zone_bypass",
            {"entry_id": entry.entry_id, "zone": 1},
            blocking=True,
        )
    assert raised.value.translation_key == "not_loaded"


async def test_arming_without_any_code_is_a_validation_error(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4, user_code="")
    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            "alarm_control_panel",
            "alarm_disarm",
            {"entity_id": alarm_entity_id},
            blocking=True,
        )
    assert raised.value.translation_key == "no_code"
    assert not [d for c, d in fake_server.received if c == "03"]
    await unload_entry(hass, entry)


async def test_disarm_types_the_default_code(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=4, user_code="1234")
    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    await hass.services.async_call(
        "alarm_control_panel", "alarm_disarm", {"entity_id": alarm_entity_id}, blocking=True
    )
    await asyncio.sleep(0.05)
    keys = "".join(d.split(",", 1)[1] for c, d in fake_server.received if c == "03")
    assert keys == "12341"
    await unload_entry(hass, entry)


async def test_diagnostics_redact_every_code(hass, fake_server):
    entry = await setup_entry(
        hass, fake_server, num_zones=4, options={"installer_code": "4112", "user_code": "1234"}
    )
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["config_entry"]["data"]["password"] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"]["user_code"] == "**REDACTED**"
    assert diagnostics["config_entry"]["options"]["installer_code"] == "**REDACTED**"
    assert diagnostics["config_entry"]["options"]["user_code"] == "**REDACTED**"
    assert diagnostics["config_entry"]["data"]["host"] == "127.0.0.1"
    assert set(diagnostics["zones"]) == {"1", "2", "3", "4"}
    assert diagnostics["last_event"]["name"] == "dump_zone_timers_ack"
    text = str(diagnostics)
    assert "4112" not in text
    assert "1234" not in text
    await unload_entry(hass, entry)
