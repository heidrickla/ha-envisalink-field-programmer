"""Regression checks for rejected reports and Program Mode save boundaries."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component

from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.envisalink_field_programmer.models import KeypadUse, ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import ModeEvent

from .conftest import unload_entry
from .test_program_mode_recovery import _issue, _setup, _until


def test_storage_abort_text_explains_save_failure_and_action() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "custom_components/envisalink_field_programmer/translations/en.json"
    )
    en = json.loads(path.read_text(encoding="utf-8"))
    text = en["issues"]["program_mode_unknown"]["fix_flow"]["abort"]["storage_failed"]
    assert "could not be saved" in text
    assert "Check Home Assistant storage" in text
    assert "try again" in text


async def test_rejected_keypad_report_logs_field_without_alpha_and_counts(
    hass, fake_server, caplog
) -> None:
    entry = await _setup(hass, fake_server)
    secret = "JANE DOE BEDROOM"
    for _ in range(2):
        await fake_server.push("00", f"01,zzzz,0,00,{secret}")
    await _until(
        lambda: entry.runtime_data.rejected_keypad_updates.get("icon_led_hex") == 2
    )
    warnings = [r.message for r in caplog.records if "Rejected %00" in r.message]
    assert warnings == ["Rejected %00 keypad update: invalid icon_led_hex (length 4)"]
    assert secret not in caplog.text
    diagnostics = await async_get_config_entry_diagnostics(hass, entry)
    assert diagnostics["rejected_keypad_updates"] == {"icon_led_hex": 2}
    assert secret not in str(diagnostics)
    await unload_entry(hass, entry)


@pytest.mark.parametrize("save_fails", [False, True])
async def test_628_during_pending_confirm_is_replayed_with_unique_revisions(
    hass, fake_server, monkeypatch, save_fails
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("9")
    generation, revision = coordinator._mode.generation, coordinator._mode.revision
    assert generation is not None
    entered = asyncio.Event()
    release = asyncio.Event()
    writes: list[int] = []
    original = Store.async_save

    async def held_closed(self, data):
        if data.get("mode") == "closed":
            writes.append(int(data["revision"]))
            if not entered.is_set():
                entered.set()
                await release.wait()
                if save_fails:
                    raise OSError("disk full")
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", held_closed)
    confirm = asyncio.create_task(
        coordinator.async_confirm_program_mode_closed(generation, revision)
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await fake_server.push("03", "162801000")
        await _until(
            lambda: (
                bool(coordinator._pending_mode_events)
                or coordinator._mode.revision > revision
            )
        )
        assert coordinator._pending_mode_events or coordinator._mode.revision > revision
    finally:
        release.set()
    # The report superseded the flow while its save was in flight.
    with pytest.raises(ValueError):
        await confirm
    await coordinator._await_mode_saved()
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert coordinator._mode.revision >= revision + 2
    assert writes == [revision + 1, revision + 2]
    assert not coordinator._less_cautious_pending
    assert coordinator._mode_save_error_revision is None
    await unload_entry(hass, entry)


async def test_reports_during_pending_confirm_keep_arrival_order(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("9")
    generation, revision = coordinator._mode.generation, coordinator._mode.revision
    assert generation is not None
    entered = asyncio.Event()
    release = asyncio.Event()
    writes: list[tuple[int, str]] = []
    original = Store.async_save

    async def held_closed(self, data):
        writes.append((int(data["revision"]), str(data["mode"])))
        if data.get("mode") == "closed" and not entered.is_set():
            entered.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", held_closed)
    confirm = asyncio.create_task(
        coordinator.async_confirm_program_mode_closed(generation, revision)
    )
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await fake_server.push("03", "162801000")
        await _until(lambda: len(coordinator._pending_mode_events) == 1)
        await fake_server.push("03", "162701000")
        await _until(lambda: len(coordinator._pending_mode_events) == 2)
        assert len(coordinator._pending_mode_events) == 2
    finally:
        release.set()
    with pytest.raises(ValueError):
        await confirm
    await coordinator._await_mode_saved()
    assert coordinator.program_mode is ProgramMode.OPEN
    assert writes == [
        (revision + 1, "closed"),
        (revision + 2, "closed"),
        (revision + 3, "open"),
    ]
    await unload_entry(hass, entry)


async def test_cancellation_during_keypad_finish_propagates_after_release(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    entered = asyncio.Event()
    release = asyncio.Event()
    original = coordinator._finish_keypad

    async def held_finish(keypad):
        entered.set()
        await release.wait()
        await original(keypad)

    monkeypatch.setattr(coordinator, "_finish_keypad", held_finish)

    async def use_keypad():
        async with coordinator.async_keypad(1):
            pass

    caller = asyncio.create_task(use_keypad())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        caller.cancel()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert coordinator._keypad_holder is None
    await unload_entry(hass, entry)


async def test_finish_releases_operation_even_if_no_key_cleanup_raises(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data

    async def broken_no_key(_keypad):
        raise OSError("save failed")

    monkeypatch.setattr(coordinator, "_no_key_sent", broken_no_key)
    with pytest.raises(OSError):
        async with coordinator.async_keypad(1, KeypadUse.INSTALLER):
            pass
    assert coordinator._typing_holder is None
    assert coordinator._keypad_holder is None
    assert coordinator._mode.operation_id is None
    await unload_entry(hass, entry)


async def test_sync_failure_before_save_releases_keypad(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data

    def fail_sync():
        raise OSError("issue registry failed")

    monkeypatch.setattr(coordinator, "_sync_mode", fail_sync)
    with pytest.raises(OSError):
        async with coordinator.async_keypad(1, KeypadUse.INSTALLER):
            pass
    assert coordinator._typing_holder is None
    assert coordinator._keypad_holder is None
    assert coordinator._mode.operation_id is None
    await unload_entry(hass, entry)


async def test_no_key_sent_waits_for_pending_doubt_save(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    entered = asyncio.Event()
    release = asyncio.Event()
    finishing = asyncio.Event()
    original = Store.async_save
    original_finish = coordinator._finish_keypad

    async def hold_doubt(self, data):
        if data.get("mode") == "doubt" and not entered.is_set():
            entered.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", hold_doubt)

    async def marked_finish(keypad):
        finishing.set()
        await original_finish(keypad)

    monkeypatch.setattr(coordinator, "_finish_keypad", marked_finish)

    async def operation():
        async with coordinator.async_keypad(1, KeypadUse.INSTALLER):
            pass

    task = asyncio.create_task(operation())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        task.cancel()
        await asyncio.wait_for(finishing.wait(), 1)
        await asyncio.sleep(0)
        assert not task.done()
        assert coordinator.program_mode is ProgramMode.DOUBT
        assert coordinator._mode.operation_id is not None
        assert not coordinator._less_cautious_pending
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await coordinator._await_mode_saved()
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert coordinator._mode.operation_id is None
    await unload_entry(hass, entry)


async def test_repair_rejects_newer_closed_revision_after_successful_save(
    hass, fake_server, monkeypatch
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("9")
    generation, revision = coordinator._mode.generation, coordinator._mode.revision
    assert generation is not None
    original = Store.async_save
    injected = False

    async def save_then_reconnect(self, data):
        nonlocal injected
        await original(self, data)
        if data.get("mode") == "closed" and not injected:
            injected = True
            coordinator._transition(ModeEvent.RECONNECT)

    monkeypatch.setattr(Store, "async_save", save_then_reconnect)
    with pytest.raises(ValueError):
        await coordinator.async_confirm_program_mode_closed(generation, revision)
    await coordinator._await_mode_saved()
    assert injected
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert coordinator._durable_revision >= revision + 2
    await unload_entry(hass, entry)


@pytest.mark.parametrize("save_fails", [False, True])
async def test_repair_reports_save_failure_separately_from_stale(
    hass, fake_server, monkeypatch, save_fails
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("9")
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    original = Store.async_save

    async def save(self, data):
        if save_fails and data.get("mode") == "closed":
            raise OSError("disk full")
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", save)
    result = await manager.async_configure(flow["flow_id"], {})
    if save_fails:
        assert result["type"] == "abort"
        assert result["reason"] == "storage_failed"
        assert coordinator.program_mode is ProgramMode.DOUBT
        assert _issue(hass, entry) is not None
    else:
        assert result["type"] == "create_entry"
        assert coordinator.program_mode is ProgramMode.CLOSED
    await unload_entry(hass, entry)
