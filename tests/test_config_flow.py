"""Tests for the config flow, against a fake TPI server (no mocking of our
own connection logic -- this exercises the real login handshake)."""
from __future__ import annotations

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.vista_console.const import DOMAIN

from .helpers import FakeEnvisalinkServer

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def fake_server():
    server = FakeEnvisalinkServer(password="user")
    await server.start()
    yield server
    await server.stop()


async def test_user_flow_success(hass, fake_server):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "127.0.0.1",
            "port": fake_server.port,
            "password": "user",
            "user_code": "1234",
            "num_partitions": 1,
            "num_zones": 8,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["host"] == "127.0.0.1"

    # Explicitly unload (rather than relying on fixture teardown ordering)
    # so the coordinator's background tasks are stopped before fake_server
    # goes away -- see helpers.py / coordinator.py for why that matters.
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_user_flow_invalid_auth(hass, fake_server):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "127.0.0.1",
            "port": fake_server.port,
            "password": "wrong",
            "user_code": "",
            "num_partitions": 1,
            "num_zones": 8,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "127.0.0.1",
            "port": 1,
            "password": "user",
            "user_code": "",
            "num_partitions": 1,
            "num_zones": 8,
        },
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
