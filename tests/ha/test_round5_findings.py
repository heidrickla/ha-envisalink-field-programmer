"""Real keypad frames and cancellation at the shared Program Mode save."""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.helpers.storage import Store

from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.models import KeypadUse, ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import ModeEvent

from .conftest import unload_entry
from .test_program_mode_recovery import _issue, _setup, _typed, _until

CID_628 = "162801000"


async def _doubt(hass, fake_server, entry):
    fake_server.program_mode_entry = None
    async with entry.runtime_data.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("9")
    assert _issue(hass, entry) is not None


async def _flow(hass, entry):
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    return manager, flow


@pytest.mark.parametrize("newer", [False, True])
async def test_repair_flow_aborts_if_closed_is_not_visible(
    hass, fake_server, monkeypatch, newer
):
    entry = await _setup(hass, fake_server)
    await _doubt(hass, fake_server, entry)
    coordinator = entry.runtime_data
    manager, flow = await _flow(hass, entry)
    original = Store.async_save
    injected = False

    async def closed_save(self, data):
        nonlocal injected
        if data.get("mode") == "closed":
            if newer and not injected:
                injected = True
                coordinator._transition(ModeEvent.RECONNECT)
            elif not newer:
                raise OSError("disk full")
        await original(self, data)

    with monkeypatch.context() as patch:
        patch.setattr(Store, "async_save", closed_save)
        result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == ("stale_repair" if newer else "storage_failed")
    assert coordinator.program_mode is (
        ProgramMode.CLOSED if newer else ProgramMode.DOUBT
    )
    assert (_issue(hass, entry) is not None) is not newer
    await unload_entry(hass, entry)


@pytest.mark.parametrize("use", [KeypadUse.PROGRAMMING, KeypadUse.INSTALLER])
async def test_cancelled_doubt_save_releases_holders_and_allows_next_operation(
    hass, fake_server, monkeypatch, use
):
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def held_save(self, data):
        if data.get("mode") == "doubt" and not saving.is_set():
            saving.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", held_save)
    finishing = asyncio.Event()
    real_finish = coordinator._finish_keypad

    async def marked_finish(keypad):
        finishing.set()
        await real_finish(keypad)

    monkeypatch.setattr(coordinator, "_finish_keypad", marked_finish)

    async def operation():
        async with coordinator.async_keypad(1, use):
            pass

    task = asyncio.create_task(operation())
    try:
        await asyncio.wait_for(saving.wait(), 1)
        task.cancel()
        await asyncio.wait_for(finishing.wait(), 1)
        task.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        await coordinator._await_mode_saved()
        assert coordinator._typing_holder is None
        assert coordinator._keypad_holder is None
        assert coordinator.program_mode is ProgramMode.CLOSED
        async with coordinator.async_keypad(1) as keypad:
            await keypad("1")
        assert _typed(fake_server) == "1"
        await fake_server.push("03", CID_628)
        await _until(lambda: coordinator.program_mode is ProgramMode.CLOSED)
    finally:
        release.set()
    await unload_entry(hass, entry)


async def test_cancelled_repair_save_does_not_poison_later_628(
    hass, fake_server, monkeypatch
):
    entry = await _setup(hass, fake_server)
    await _doubt(hass, fake_server, entry)
    coordinator = entry.runtime_data
    generation, revision = coordinator._mode.generation, coordinator._mode.revision
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def held_closed(self, data):
        if data.get("mode") == "closed" and not saving.is_set():
            saving.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", held_closed)
    assert generation is not None
    confirm = asyncio.create_task(
        coordinator.async_confirm_program_mode_closed(generation, revision)
    )
    try:
        await asyncio.wait_for(saving.wait(), 1)
        confirm.cancel()
        with pytest.raises(asyncio.CancelledError):
            await confirm
        await fake_server.push("03", CID_628)
    finally:
        release.set()
    await coordinator._await_mode_saved()
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert not coordinator._less_cautious_pending
    async with coordinator.async_keypad(1) as keypad:
        await keypad("1")
    await unload_entry(hass, entry)


async def test_cancelled_everyday_caller_cannot_cancel_pending_mode_save(
    hass, fake_server, monkeypatch
):
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def held_closed(self, data):
        if data.get("mode") == "closed" and not saving.is_set():
            saving.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", held_closed)

    async def everyday():
        async with coordinator.async_keypad(1):
            await fake_server.push("03", "162701000")
            await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
            await fake_server.push("03", CID_628)
            await saving.wait()
            await coordinator._await_mode_saved()

    task = asyncio.create_task(everyday())
    try:
        await asyncio.wait_for(saving.wait(), 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
    await coordinator._await_mode_saved()
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert coordinator._keypad_holder is None
    async with coordinator.async_keypad(1) as keypad:
        await keypad("1")
    await unload_entry(hass, entry)


@pytest.mark.parametrize("failure", ["cancelled", "raised"])
async def test_a_dead_save_predecessor_does_not_poison_later_628(
    hass, fake_server, failure
):
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    prior = asyncio.create_task(asyncio.sleep(0))
    await prior
    if failure == "cancelled":
        prior = asyncio.create_task(asyncio.sleep(10))
        prior.cancel()
        with pytest.raises(asyncio.CancelledError):
            await prior
    else:

        async def broken():
            raise OSError("old save failed")

        prior = asyncio.create_task(broken())
        with pytest.raises(OSError):
            await prior
    coordinator._mode_save_task = prior
    await fake_server.push("03", CID_628)
    await _until(lambda: coordinator._mode_save_task is not prior)
    next_save = coordinator._mode_save_task
    assert next_save is not None
    await _until(next_save.done)
    try:
        assert not next_save.cancelled()
        assert next_save.exception() is None
        assert coordinator.program_mode is ProgramMode.CLOSED
        async with coordinator.async_keypad(1) as keypad:
            await keypad("1")
    finally:
        if next_save.cancelled() or next_save.exception() is not None:
            coordinator._mode_save_task = None
        await unload_entry(hass, entry)


async def test_cancelling_a_successor_does_not_overtake_its_pending_save(
    hass, fake_server, monkeypatch
):
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    saving = asyncio.Event()
    release = asyncio.Event()
    writes = []
    original = Store.async_save

    async def held_first(self, data):
        writes.append(data["revision"])
        if not saving.is_set():
            saving.set()
            await release.wait()
        await original(self, data)

    monkeypatch.setattr(Store, "async_save", held_first)
    coordinator._transition(ModeEvent.RECONNECT)
    first_revision = coordinator._mode.revision
    first = coordinator._mode_save_task
    assert first is not None
    try:
        await asyncio.wait_for(saving.wait(), 1)
        coordinator._transition(ModeEvent.RECONNECT)
        second = coordinator._mode_save_task
        assert second is not None
        second.cancel()
        with pytest.raises(asyncio.CancelledError):
            await second
        assert writes == [first_revision]
    finally:
        release.set()
    await first
    coordinator._transition(ModeEvent.RECONNECT)
    await coordinator._await_mode_saved()
    assert writes == [first_revision, first_revision + 2]
    await unload_entry(hass, entry)
