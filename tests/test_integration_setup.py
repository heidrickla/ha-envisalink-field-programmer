"""End-to-end test: set up the config entry against a fake TPI server and
verify entities are created and react to pushed panel events."""
from __future__ import annotations

import asyncio

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.envisalink_field_programmer.const import DOMAIN

from .helpers import FakeEnvisalinkServer

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def fake_server():
    server = FakeEnvisalinkServer(password="user")
    await server.start()
    yield server
    await server.stop()


async def _setup_entry(hass, fake_server) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "127.0.0.1",
            "port": fake_server.port,
            "password": "user",
            "user_code": "1234",
            "num_partitions": 1,
            "num_zones": 4,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass, entry: MockConfigEntry, domain: str, suffix: str) -> str:
    registry = er.async_get(hass)
    unique_id = f"{entry.entry_id}_{suffix}"
    entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
    assert entity_id is not None, f"no entity registered for unique_id={unique_id!r}"
    return entity_id


async def _unload(hass, entry: MockConfigEntry) -> None:
    # Explicitly unload (rather than relying on fixture teardown ordering)
    # so the coordinator's background tasks are stopped before fake_server
    # goes away -- see helpers.py / coordinator.py for why that matters.
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_entities_created_and_default_state(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)

    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    alarm_state = hass.states.get(alarm_entity_id)
    assert alarm_state is not None
    assert alarm_state.state == "disarmed"

    zone_entity_id = _entity_id(hass, entry, "binary_sensor", "zone_1")
    zone_state = hass.states.get(zone_entity_id)
    assert zone_state is not None
    assert zone_state.state == "off"

    await _unload(hass, entry)


async def test_arm_event_updates_alarm_entity(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    # Icon LED bits: armed_away (bit 2) + ac_present (bit 3) = 0xC.
    await fake_server.push("00", "1,c,0,00,ARMED AWAY")
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()

    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    assert hass.states.get(alarm_entity_id).state == "armed_away"

    await _unload(hass, entry)


async def test_zone_open_event_updates_binary_sensor(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    # Zone timer dump, 4 zones: zone 2's chunk (FEFF, little-endian) decodes
    # to 1 tick since last fault -- recently faulted, so considered open.
    hex_string = "0000" + "FEFF" + "0000" + "0000"
    await fake_server.push("FF", hex_string)
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()

    zone_entity_id = _entity_id(hass, entry, "binary_sensor", "zone_2")
    assert hass.states.get(zone_entity_id).state == "on"

    await _unload(hass, entry)


async def test_disconnect_marks_entities_unavailable(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await fake_server.stop()
    await asyncio.sleep(0.1)
    await hass.async_block_till_done()

    alarm_entity_id = _entity_id(hass, entry, "alarm_control_panel", "partition_1")
    assert hass.states.get(alarm_entity_id).state == "unavailable"

    await _unload(hass, entry)
