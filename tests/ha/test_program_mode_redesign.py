"""Concrete panel sequences from the Program Mode blind review."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component

from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.models import KeypadUse, ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import ModeEvent
from custom_components.envisalink_field_programmer.programming import (
    async_send_guarded_keystrokes,
)

from .conftest import unload_entry
from .test_program_mode_recovery import (
    _disarm,
    _issue,
    _program_key_a,
    _setup,
    _typed,
    _until,
)


async def test_old_repair_cannot_close_a_new_operation_while_an_ack_is_held(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    await async_send_guarded_keystrokes(coordinator, 1, "9", allow_installer_mode=True)
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    assert flow["step_id"] == "confirm"
    await fake_server.push("03", "1628" + "01" + "000")
    await _until(lambda: coordinator.program_mode is ProgramMode.CLOSED)
    before = len(_typed(fake_server))
    fake_server.scripted_responses["03"] = ["00"] * 7 + [None]
    operation = asyncio.create_task(_program_key_a(hass, entry))
    await _until(lambda: len(_typed(fake_server)) == before + 8)
    assert fake_server.in_program_mode
    result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "operation_in_progress"
    assert coordinator.program_mode is ProgramMode.OPEN
    await fake_server.release_held_acks()
    await operation
    assert coordinator.program_mode is ProgramMode.CLOSED
    await unload_entry(hass, entry)


async def test_old_repair_flow_cannot_settle_a_new_idle_doubt(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    await async_send_guarded_keystrokes(coordinator, 1, "9", allow_installer_mode=True)
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    old_flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    await fake_server.push("03", "1628" + "01" + "000")
    await _until(lambda: coordinator.program_mode is ProgramMode.CLOSED)
    await async_send_guarded_keystrokes(coordinator, 1, "9", allow_installer_mode=True)
    result = await manager.async_configure(old_flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "stale_repair"
    assert coordinator.program_mode is ProgramMode.DOUBT
    await unload_entry(hass, entry)


async def test_repair_cannot_confirm_while_an_ordinary_writer_holds_keypad(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = [None]
    disarm = asyncio.create_task(_disarm(hass, entry))
    await _until(lambda: _typed(fake_server) == "1")
    await fake_server.push("03", "1627" + "01" + "000")
    await _until(lambda: _issue(hass, entry) is not None)
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "operation_in_progress"
    await fake_server.release_held_acks()
    with pytest.raises(HomeAssistantError):
        await disarm
    assert entry.runtime_data.program_mode is ProgramMode.OPEN
    await unload_entry(hass, entry)


async def test_open_report_survives_disconnect_then_armed_report(
    hass, fake_server, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_BACKOFF_MIN",
        0.05,
    )
    entry = await _setup(hass, fake_server)
    fake_server.drop_on = "4112800*57"
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert fake_server.in_program_mode
    await _until(
        lambda: (
            fake_server.connections >= 2
            and entry.runtime_data.data.system.connected
            and not fake_server._writer.is_closing()
        )
    )
    await fake_server.push("00", "1,000C,0,00,ARMED AWAY")
    await _until(lambda: entry.runtime_data.data.partitions[1].armed)
    assert entry.runtime_data.program_mode is ProgramMode.DOUBT
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.data["saw_627"] is True
    generation = issue.data["generation"]
    await entry.runtime_data._await_mode_saved()
    stored = await entry.runtime_data._mode_store.async_load()
    assert stored is not None
    assert stored["saw_627"] is True
    assert stored["generation"] == generation
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data._mode.saw_627
    assert entry.runtime_data._mode.generation == generation
    assert entry.runtime_data.program_mode is ProgramMode.DOUBT
    await unload_entry(hass, entry)


async def test_partition_armed_during_outage_is_refused_after_reconnect(
    hass, fake_server, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_BACKOFF_MIN",
        0.05,
    )
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.drop_on = "1"
    with pytest.raises(HomeAssistantError):
        await async_send_guarded_keystrokes(coordinator, 1, "1")
    await _until(
        lambda: (
            fake_server.connections >= 2
            and coordinator.data.system.connected
            and not fake_server._writer.is_closing()
        )
    )
    before = _typed(fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "partition_report_pending"
    assert _typed(fake_server) == before
    await fake_server.push("00", "1,000C,0,00,ARMED AWAY")
    await _until(lambda: coordinator.data.partitions[1].armed)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "partition_armed"
    assert _typed(fake_server) == before
    await unload_entry(hass, entry)


async def test_doubt_save_finishes_before_first_key(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def hold_doubt(self, data):
        if isinstance(data, dict) and data.get("mode") == "doubt":
            saving.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", hold_doubt)
    operation = asyncio.create_task(_program_key_a(hass, entry))
    try:
        await asyncio.wait_for(saving.wait(), timeout=1)
        assert _typed(fake_server) == ""
    finally:
        release.set()
    await operation
    await unload_entry(hass, entry)


async def test_failed_doubt_save_blocks_the_first_key(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    original = Store.async_save

    async def lose_doubt(self, data):
        if isinstance(data, dict) and data.get("mode") == "doubt":
            return
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", lose_doubt)
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_storage_failed"
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_held_keypad_counts_accepted_keys_after_overrun(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = ["01", None]
    async with entry.runtime_data.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        task = asyncio.create_task(keypad("1"))
        await _until(
            lambda: len([c for c, _ in fake_server.received if c == "03"]) == 2
        )
        assert keypad.written == 0
        await fake_server.release_held_acks()
        await task
        assert keypad.written == 1
    await unload_entry(hass, entry)


async def test_installer_send_holds_doubt_against_an_armed_report(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = [None]
    send = asyncio.create_task(
        async_send_guarded_keystrokes(
            entry.runtime_data, 1, "1", allow_installer_mode=True
        )
    )
    await _until(lambda: _typed(fake_server) == "1")
    await fake_server.push("00", "1,000C,0,00,ARMED AWAY")
    await _until(lambda: entry.runtime_data.data.partitions[1].armed)
    assert entry.runtime_data.program_mode is ProgramMode.DOUBT
    await fake_server.release_held_acks()
    await send
    await unload_entry(hass, entry)


@pytest.mark.parametrize("boundary", [ModeEvent.DISCONNECT, ModeEvent.RECONNECT])
async def test_session_boundary_during_entry_stops_remaining_keys(
    hass, fake_server, boundary
) -> None:
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = ["00", None]
    operation = asyncio.create_task(_program_key_a(hass, entry))
    await _until(lambda: _typed(fake_server) == "41")
    entry.runtime_data._transition(boundary)
    await fake_server.release_held_acks()
    with pytest.raises(HomeAssistantError) as raised:
        await operation
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == "41"
    await unload_entry(hass, entry)


async def test_second_627_after_entry_stops_next_menu_key(hass, fake_server) -> None:
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = ["00"] * 8 + [None]
    operation = asyncio.create_task(_program_key_a(hass, entry))
    await _until(lambda: _typed(fake_server) == "4112800*5")
    await fake_server.push("03", "1627" + "01" + "000")
    await _until(lambda: entry.runtime_data.program_mode_changes >= 3)
    await fake_server.release_held_acks()
    with pytest.raises(HomeAssistantError) as raised:
        await operation
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == "4112800*5"
    await unload_entry(hass, entry)


async def test_overrun_retry_rechecks_the_menu_gate(
    hass, fake_server, monkeypatch
) -> None:
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.client.COMMAND_RETRY_DELAY",
        0.2,
    )
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = ["00"] * 7 + ["01", "00"]
    operation = asyncio.create_task(_program_key_a(hass, entry))
    await _until(lambda: _typed(fake_server) == "4112800*")
    await fake_server.push("03", "1628" + "01" + "000")
    await _until(lambda: entry.runtime_data.program_mode is ProgramMode.CLOSED)
    with pytest.raises(HomeAssistantError) as raised:
        await operation
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == "4112800*"
    await unload_entry(hass, entry)
