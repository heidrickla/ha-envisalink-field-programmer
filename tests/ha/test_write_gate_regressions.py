"""Reproductions of the four write-boundary failures."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store

from custom_components.envisalink_field_programmer.client import TPICommandRefused
from custom_components.envisalink_field_programmer.models import KeypadUse, ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import ModeState

from .conftest import unload_entry
from .test_program_mode_recovery import _program_key_a, _setup, _typed, _until


@pytest.mark.parametrize("icon", ["", "zz"])
async def test_corrupt_icon_cannot_make_partition_fresh_or_start_guided_entry(
    hass, fake_server, monkeypatch, icon
) -> None:
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.PARTITION_REPORT_TIMEOUT",
        0.1,
    )
    fake_server.answer_partition_requests = False
    entry = await _setup(hass, fake_server)
    await fake_server.push("00", f"1,{icon},0,00,READY")
    await asyncio.sleep(0.02)
    assert not entry.runtime_data.data.partitions[1].fresh
    with pytest.raises(ServiceValidationError):
        await _program_key_a(hass, entry)
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_foreign_627_during_first_key_overrun_backoff_stops_installer(
    hass, fake_server, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.client.COMMAND_RETRY_DELAY", 0.2
    )
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = ["01", "00"]
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        send = asyncio.create_task(keypad("12"))
        await _until(
            lambda: len([c for c, _ in fake_server.received if c == "03"]) == 1
        )
        await fake_server.push("03", "162701000")
        await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
        with pytest.raises(HomeAssistantError):
            await send
        assert keypad.written == 0
        assert len([c for c, _ in fake_server.received if c == "03"]) == 1
    await unload_entry(hass, entry)


@pytest.mark.parametrize("fresh_again", [False, True])
async def test_everyday_holder_cannot_resume_after_release_and_reconnect(
    hass, fake_server, fresh_again
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1) as keypad:
        await keypad("1")
        fake_server.answer_partition_requests = False
        await coordinator.async_release_session()
        await coordinator.async_resume_session()
        assert not coordinator.data.partitions[1].fresh
        if fresh_again:
            await fake_server.push("00", "1,1008,0,00,READY")
            await _until(lambda: coordinator.data.partitions[1].fresh)
        with pytest.raises((HomeAssistantError, ServiceValidationError)):
            await keypad("2")
    assert _typed(fake_server) == "1"
    await unload_entry(hass, entry)


async def test_a_freshness_loss_on_the_same_session_stops_the_next_key(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1) as keypad:
        await keypad("1")
        coordinator.data.partitions[1].fresh = False
        with pytest.raises(ServiceValidationError) as raised:
            await keypad("2")
        assert raised.value.translation_key == "partition_report_pending"
    assert _typed(fake_server) == "1"
    await unload_entry(hass, entry)


async def test_a_late_report_during_release_cannot_authorize_a_new_key(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    disconnect_started = asyncio.Event()
    finish_disconnect = asyncio.Event()
    original_disconnect = coordinator.client.disconnect

    async def held_disconnect() -> None:
        disconnect_started.set()
        await finish_disconnect.wait()
        await original_disconnect()

    monkeypatch.setattr(coordinator.client, "disconnect", held_disconnect)
    releasing = asyncio.create_task(coordinator.async_release_session())
    try:
        await asyncio.wait_for(disconnect_started.wait(), timeout=1)
        await fake_server.push("00", "1,1008,0,00,READY")
        await _until(lambda: coordinator.data.partitions[1].fresh)
        async with coordinator.async_keypad(1) as keypad:
            with pytest.raises(HomeAssistantError):
                await keypad("1")
        assert _typed(fake_server) == ""
    finally:
        finish_disconnect.set()
    await releasing
    await unload_entry(hass, entry)


async def test_a_key_waits_while_a_less_cautious_state_save_is_pending(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("1")
        await fake_server.push("03", "162701000")
        await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)

        saving = asyncio.Event()
        release = asyncio.Event()
        original = Store.async_save

        async def hold_closed(self, data):
            if isinstance(data, dict) and data.get("mode") == "closed":
                saving.set()
                await release.wait()
            await original(self, data)

        monkeypatch.setattr(Store, "async_save", hold_closed)
        await fake_server.push("03", "162801000")
        try:
            await asyncio.wait_for(saving.wait(), timeout=1)
            with pytest.raises(HomeAssistantError):
                await keypad("2")
            assert _typed(fake_server) == "1"
        finally:
            release.set()
    await unload_entry(hass, entry)


async def test_disconnected_client_cannot_write_with_a_fresh_report(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    monkeypatch.setattr(
        type(coordinator.client), "connected", property(lambda _: False)
    )
    async with coordinator.async_keypad(1) as keypad:
        with pytest.raises(HomeAssistantError):
            await keypad("1")
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_no_key_sent_is_durable_before_closed_is_visible(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def hold_closed(self, data):
        if isinstance(data, dict) and data.get("mode") == "closed":
            saving.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", hold_closed)
    fake_server.scripted_responses["03"] = ["02"]

    async def attempt() -> None:
        async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
            with pytest.raises(TPICommandRefused):
                await keypad("1")

    task = asyncio.create_task(attempt())
    try:
        await asyncio.wait_for(saving.wait(), timeout=1)
        assert coordinator.program_mode is ProgramMode.DOUBT
        stored = await coordinator._mode_store.async_load()
        assert stored is not None
        assert ModeState.restore(stored).mode is ProgramMode.DOUBT
    finally:
        release.set()
    await task
    await coordinator._await_mode_saved()
    assert coordinator.program_mode is ProgramMode.CLOSED
    stored = await coordinator._mode_store.async_load()
    assert stored is not None
    assert ModeState.restore(stored).mode is ProgramMode.CLOSED
    await unload_entry(hass, entry)
