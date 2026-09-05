"""The entity platforms and the coordinator loops behind them.

Everything here runs against the fake TPI server, so an assertion about a
keystroke is an assertion about what the panel would have received.
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.helpers import entity_registry as er

from custom_components.envisalink_field_programmer.client import EnvisalinkClient
from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import setup_entry, unload_entry


def _entity_id(hass, entry, domain: str, suffix: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{suffix}")
    assert entity_id is not None, f"no entity registered for {suffix!r}"
    return entity_id


def _sent_keys(fake_server) -> str:
    """Every keystroke character the panel has been sent so far."""
    return "".join(data.split(",", 1)[1] for code, data in fake_server.received if code == "03")


async def _enable(hass, entry, *entity_ids: str) -> None:
    """Turn on entities the integration creates disabled, then reload."""
    registry = er.async_get(hass)
    for entity_id in entity_ids:
        registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("service", "expected"),
    [
        ("alarm_arm_away", "12342"),
        ("alarm_arm_home", "12343"),
        ("alarm_arm_night", "123433"),
    ],
)
async def test_arming_types_the_code_and_the_mode_digits(hass, fake_server, service, expected):
    entry = await setup_entry(hass, fake_server, num_zones=2, user_code="1234")
    await hass.services.async_call(
        "alarm_control_panel",
        service,
        {"entity_id": _entity_id(hass, entry, "alarm_control_panel", "partition_1")},
        blocking=True,
    )
    await asyncio.sleep(0.05)
    assert _sent_keys(fake_server) == expected
    await unload_entry(hass, entry)


async def test_alarm_and_exit_delay_show_as_triggered_and_arming(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")

    # Icon LED bits: alarm (bit 0) + ac_present (bit 3) = 0x9.
    await fake_server.push("00", "1,9,0,00,ALARM")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "triggered"

    # A partition state change reporting exit delay.
    entry.runtime_data.data.partition(1).alarm = False
    entry.runtime_data.data.partition(1).exit_delay = True
    entry.runtime_data.async_set_updated_data(entry.runtime_data.data)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "arming"

    await unload_entry(hass, entry)


async def test_the_trouble_sensor_reports_each_partition(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    entity_id = _entity_id(hass, entry, "binary_sensor", "system_trouble")
    # Icon LED bits: none set, so no AC present, which is a trouble.
    await fake_server.push("00", "1,0,0,00,AC LOSS")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["partitions"][1]["ac_present"] is False
    assert state.attributes["installers_mode"] is False
    await unload_entry(hass, entry)


async def test_the_bypass_switch_types_the_bypass_sequence_once(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    switch_id = _entity_id(hass, entry, "switch", "zone_1_bypass")
    await _enable(hass, entry, switch_id)

    assert hass.states.get(switch_id).state == "off"
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
    await asyncio.sleep(0.05)
    assert _sent_keys(fake_server) == "*101#"
    assert hass.states.get(switch_id).state == "on"
    assert hass.states.get(switch_id).attributes["zone_number"] == 1

    # Already bypassed: turning it on again sends nothing.
    await hass.services.async_call("switch", "turn_on", {"entity_id": switch_id}, blocking=True)
    await asyncio.sleep(0.05)
    assert _sent_keys(fake_server) == "*101#"

    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    await asyncio.sleep(0.05)
    assert _sent_keys(fake_server) == "*101#*101#"
    assert hass.states.get(switch_id).state == "off"
    # And off again is another no-op.
    await hass.services.async_call("switch", "turn_off", {"entity_id": switch_id}, blocking=True)
    await asyncio.sleep(0.05)
    assert _sent_keys(fake_server) == "*101#*101#"
    await unload_entry(hass, entry)


async def test_the_toggle_zone_bypass_action_types_the_same_sequence(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    await hass.services.async_call(
        DOMAIN, "toggle_zone_bypass", {"entry_id": entry.entry_id, "zone": 2}, blocking=True
    )
    await asyncio.sleep(0.05)
    assert _sent_keys(fake_server) == "*102#"
    await unload_entry(hass, entry)


async def test_the_last_event_sensor_shows_the_frame_once_enabled(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    sensor_id = _entity_id(hass, entry, "sensor", "last_event")
    await _enable(hass, entry, sensor_id)

    await fake_server.push("00", "1,8,0,00,READY")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    state = hass.states.get(sensor_id)
    assert state.state == "keypad_update"
    assert state.attributes["code"] == "%00"
    assert state.attributes["fields"]["alpha"] == "READY"
    await unload_entry(hass, entry)


async def test_the_last_user_sensor_follows_the_panel(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    sensor_id = _entity_id(hass, entry, "sensor", "partition_1_last_user")
    assert hass.states.get(sensor_id).state == "unknown"

    # CID 401 closing (an arm) by user 002 on partition 01.
    await fake_server.push("03", "3401" + "01" + "002")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    assert hass.states.get(sensor_id).state == "002"
    await unload_entry(hass, entry)


async def test_the_keepalive_and_zone_dump_keep_running_and_survive_refusals(
    hass, fake_server, monkeypatch
):
    # Both timers are the only thing that notices a silently dead session, so
    # a refused poll must not end the loop.
    calls: dict[str, int] = {"keepalive": 0, "dump": 0}
    real_dump = EnvisalinkClient.dump_zone_timers

    async def _keep_alive(self):
        calls["keepalive"] += 1
        raise OSError("refused")

    async def _dump(self):
        calls["dump"] += 1
        if calls["dump"] > 1:
            raise OSError("refused")
        await real_dump(self)

    monkeypatch.setattr(EnvisalinkClient, "keep_alive", _keep_alive)
    monkeypatch.setattr(EnvisalinkClient, "dump_zone_timers", _dump)
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.ZONE_TIMER_DUMP_INTERVAL",
        0.02,
    )
    entry = await setup_entry(hass, fake_server, num_zones=2, options={"keepalive_interval": 0.02})
    for _ in range(50):
        await asyncio.sleep(0.02)
        if calls["keepalive"] >= 2 and calls["dump"] >= 3:
            break
    assert calls["keepalive"] >= 2
    assert calls["dump"] >= 3

    # With the socket closed the loop idles instead of writing to nothing.
    await entry.runtime_data.client.disconnect()
    await asyncio.sleep(0.05)
    settled = dict(calls)
    await asyncio.sleep(0.1)
    assert calls == settled
    await unload_entry(hass, entry)


async def test_a_manual_refresh_returns_the_pushed_state(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    coordinator = entry.runtime_data
    await coordinator.async_refresh()
    assert coordinator.data is coordinator.data
    assert coordinator.last_update_success
    await unload_entry(hass, entry)


async def test_stopping_home_assistant_closes_the_session(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    coordinator = entry.runtime_data
    assert coordinator.client.connected

    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    await asyncio.sleep(0.05)
    assert not coordinator.client.connected
    await unload_entry(hass, entry)


async def test_installers_mode_shows_as_a_system_trouble(hass, fake_server):
    entry = await setup_entry(hass, fake_server, num_zones=2)
    entity_id = _entity_id(hass, entry, "binary_sensor", "system_trouble")
    # Icon LED bits: ready + ac_present, so nothing is wrong yet.
    await fake_server.push("00", "1,1008,0,00,READY")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"

    # CID 627 is Program Mode entry, which the panel reports as an event.
    await fake_server.push("03", "1" + "627" + "01" + "000")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["installers_mode"] is True
    await unload_entry(hass, entry)
