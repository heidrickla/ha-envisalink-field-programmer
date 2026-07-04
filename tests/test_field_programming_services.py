"""End-to-end tests for the guided field-programming services.

Verifies the services are wired correctly (schema validation, the confirm/
confirm_life_safety gates, and that the exact expected keystroke sequence
reaches the panel) against a real fake TPI server, not mocks.
"""
from __future__ import annotations

import asyncio

import pytest
import voluptuous as vol
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


async def _setup_entry(hass, fake_server, *, installer_code: str | None = "4112"):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "host": "127.0.0.1",
            "port": fake_server.port,
            "password": "user",
            "user_code": "1234",
            "num_partitions": 1,
            "num_zones": 8,
        },
        options={"installer_code": installer_code} if installer_code else {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _unload(hass, entry):
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_program_zone_sends_expected_keystrokes(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": 3,
            "zone_type": 3,  # Perimeter, not life-safety
            "partition": 1,
            "confirm": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "071"]
    full_sent = "".join(frame[1:] for frame in keystroke_frames)  # strip partition digit
    # 4112800 (enter Program Mode) + *56 zone menu: confirm=no, zone 03,
    # accept summary, type=03 (Perimeter), partition=1, report=on,
    # hardwire=EOL(default), response=350ms(default), alpha=no, exit zone
    # menu, then *99 (exit Program Mode).
    assert full_sent == "4112800*560*03**03*1*1*0*1*0*00**99"
    await _unload(hass, entry)


async def test_program_zone_requires_confirm(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 3,
                "zone_type": 3,
                "partition": 1,
                "confirm": False,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_program_zone_fire_type_requires_life_safety_confirm(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(Exception, match="life-safety"):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 5,
                "zone_type": 9,  # Fire
                "partition": 1,
                "confirm": True,
                "confirm_life_safety": False,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_program_zone_fire_type_succeeds_when_confirmed(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": 5,
            "zone_type": 9,
            "partition": 1,
            "confirm": True,
            "confirm_life_safety": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "071"]
    assert keystroke_frames  # something was sent
    await _unload(hass, entry)


async def test_program_zone_requires_installer_code_configured(hass, fake_server):
    entry = await _setup_entry(hass, fake_server, installer_code=None)
    with pytest.raises(Exception, match="installer code"):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 3,
                "zone_type": 3,
                "partition": 1,
                "confirm": True,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_set_system_timing_sends_expected_keystrokes(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "set_system_timing",
        {
            "entry_id": entry.entry_id,
            "field": "34",
            "value": 45,
            "confirm": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "071"]
    full_sent = "".join(frame[1:] for frame in keystroke_frames)
    assert full_sent == "4112800*3445**99"
    await _unload(hass, entry)


async def test_program_function_key_sends_expected_keystrokes(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "program_function_key",
        {
            "entry_id": entry.entry_id,
            "key": "A",
            "partition": 1,
            "action": 3,  # Arm Away
            "confirm": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "071"]
    full_sent = "".join(frame[1:] for frame in keystroke_frames)
    assert full_sent == "4112800*571*1*03*0*00*99"
    await _unload(hass, entry)
