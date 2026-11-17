"""The findings of the second blind review of the Program Mode state, one test each.

Each test is the sequence the review ran against the integration and the
outcome the decided behavior requires.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.components.repairs import repairs_flow_manager
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.setup import async_setup_component

from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.models import KeypadUse, ProgramMode
from custom_components.envisalink_field_programmer.program_mode_state import ModeEvent

from .conftest import unload_entry
from .test_program_mode_recovery import (
    COMPLETE,
    _issue,
    _program_key_a,
    _setup,
    _typed,
    _until,
)

CID_627 = "1627" + "01" + "000"
CID_628 = "1628" + "01" + "000"
TRANSLATIONS = (
    Path(__file__).parent.parent.parent
    / "custom_components"
    / "envisalink_field_programmer"
    / "translations"
    / "en.json"
)


def _en() -> dict:
    return json.loads(TRANSLATIONS.read_text(encoding="utf-8"))


async def _installer_send(hass, entry, keys: str) -> None:
    await hass.services.async_call(
        DOMAIN,
        "send_keystrokes",
        {
            "entry_id": entry.entry_id,
            "partition": 1,
            "keys": keys,
            "confirm_installer_risk": True,
        },
        blocking=True,
    )


async def _flow(hass, entry):
    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    assert flow["step_id"] == "confirm"
    return manager, flow


# -- M1: an installer send types past its own 627 -----------------------------


async def test_an_installer_send_types_past_the_627_its_own_entry_produced(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    await _installer_send(hass, entry, "4112800*56")
    assert _typed(fake_server) == "4112800*56"
    coordinator = entry.runtime_data
    # The panel reported Program Mode open and nothing has said it closed.
    assert coordinator.program_mode is ProgramMode.DOUBT
    assert coordinator._mode.saw_627
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_the_installer_send_binds_the_627_it_produced_to_itself(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1, KeypadUse.INSTALLER) as keypad:
        await keypad("4112800")
        await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
        assert coordinator._mode.operation_id == keypad.operation_id
        await keypad("*56")
    await unload_entry(hass, entry)


async def test_a_627_no_operation_explains_still_stops_an_installer_send(
    hass, fake_server
) -> None:
    # The 627 lands while the doubt is being saved, before any key: nothing of
    # ours can have caused it.
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def hold_doubt(self, data):
        if (
            isinstance(data, dict)
            and data.get("mode") == "doubt"
            and not saving.is_set()
        ):
            saving.set()
            await release.wait()
        await original(self, data)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Store, "async_save", hold_doubt)
        send = asyncio.create_task(_installer_send(hass, entry, "91"))
        await asyncio.wait_for(saving.wait(), timeout=1)
        await fake_server.push("03", CID_627)
        await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
        release.set()
        with pytest.raises(HomeAssistantError) as raised:
            await send
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


# -- L2: a second 627 invalidates a guided binding ----------------------------


async def test_a_second_627_leaves_the_guided_operation_unbound(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.scripted_responses["03"] = ["00"] * 8 + [None]
    operation = asyncio.create_task(_program_key_a(hass, entry))
    await _until(lambda: _typed(fake_server) == "4112800*5")
    assert coordinator._mode.operation_id is not None
    await fake_server.push("03", CID_627)
    await _until(lambda: coordinator._mode.operation_id is None)
    await fake_server.release_held_acks()
    with pytest.raises(HomeAssistantError):
        await operation
    await unload_entry(hass, entry)


async def test_a_627_before_the_last_entry_key_is_sent_binds_to_nobody(
    hass, fake_server
) -> None:
    # Six of the seven entry keys are in and acknowledged; the seventh has not
    # begun, so a 627 now cannot be the answer to it.
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1, KeypadUse.PROGRAMMING) as keypad:
        keypad.entry_length = 7
        await keypad("411280")
        await fake_server.push("03", CID_627)
        await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
        assert coordinator._mode.operation_id is None
    await unload_entry(hass, entry)


async def test_the_627_after_the_whole_entry_binds_to_the_operation(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    async with coordinator.async_keypad(1, KeypadUse.PROGRAMMING) as keypad:
        keypad.entry_length = 7
        await keypad("4112800")
        await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
        assert coordinator._mode.operation_id == keypad.operation_id
    await unload_entry(hass, entry)


# -- M2: a repair settles only the exact doubt it was opened for --------------


async def test_a_repair_opened_before_a_later_627_cannot_settle_it(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    await _installer_send(hass, entry, "9")
    manager, flow = await _flow(hass, entry)
    await fake_server.push("03", CID_627)
    await _until(lambda: coordinator.program_mode is ProgramMode.OPEN)
    result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "stale_repair"
    assert coordinator.program_mode is ProgramMode.OPEN
    # The repair now listed is the one for this state, and it settles it.
    _, current = await _flow(hass, entry)
    result = await manager.async_configure(current["flow_id"], {})
    assert result["type"] == "create_entry"
    assert coordinator.program_mode is ProgramMode.CLOSED
    await unload_entry(hass, entry)


async def test_a_repair_opened_before_any_newer_state_is_stale(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    await _installer_send(hass, entry, "9")
    manager, flow = await _flow(hass, entry)
    coordinator._transition(ModeEvent.RECONNECT)
    result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "stale_repair"
    assert coordinator.program_mode is ProgramMode.DOUBT
    await unload_entry(hass, entry)


async def test_a_repair_for_a_doubt_the_panel_already_closed_says_so(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    await _installer_send(hass, entry, "9")
    manager, flow = await _flow(hass, entry)
    await fake_server.push("03", CID_628)
    await _until(lambda: coordinator.program_mode is ProgramMode.CLOSED)
    result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "abort"
    assert result["reason"] == "already_settled"
    await unload_entry(hass, entry)


# -- M3: no doubt and no repair when no key was written ----------------------


@pytest.mark.parametrize("failure", ["dropped", "raises"])
async def test_a_failed_doubt_save_leaves_closed_and_the_retry_is_allowed(
    hass, fake_server, failure
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    original = Store.async_save
    broken = {"on": True}

    async def lose_doubt(self, data):
        if broken["on"] and isinstance(data, dict) and data.get("mode") == "doubt":
            if failure == "raises":
                raise OSError("disk full")
            return
        await original(self, data)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Store, "async_save", lose_doubt)
        with pytest.raises(HomeAssistantError) as raised:
            await _program_key_a(hass, entry)
        assert raised.value.translation_key == "program_mode_storage_failed"
        assert _typed(fake_server) == ""
        await hass.async_block_till_done()
        assert coordinator.program_mode is ProgramMode.CLOSED
        assert _issue(hass, entry) is None
        broken["on"] = False
        await _program_key_a(hass, entry)
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)


async def test_an_installer_send_with_the_session_down_raises_no_doubt(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    await coordinator.async_release_session()
    with pytest.raises(HomeAssistantError) as raised:
        await _installer_send(hass, entry, "*99")
    assert raised.value.translation_key == "keystrokes_not_accepted"
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert _issue(hass, entry) is None
    assert _typed(fake_server) == ""
    await coordinator.async_resume_session()
    await unload_entry(hass, entry)


async def test_a_guided_operation_stopped_before_its_first_write_raises_no_doubt(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    # A command holds the lock, so the first key waits for its turn.
    fake_server.scripted_responses["00"] = [None]
    keepalive = asyncio.ensure_future(coordinator.client.keep_alive())
    await _until(lambda: ("00", "") in fake_server.received)
    operation = asyncio.create_task(_program_key_a(hass, entry))
    await _until(lambda: coordinator.data.system.installers_mode)
    operation.cancel()
    with pytest.raises(asyncio.CancelledError):
        await operation
    await fake_server.release_held_acks()
    await keepalive
    assert _typed(fake_server) == ""
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert _issue(hass, entry) is None
    await unload_entry(hass, entry)


async def test_a_key_written_without_its_acknowledgement_keeps_the_doubt(
    hass, fake_server, monkeypatch
) -> None:
    # The key may have been typed, so the doubt is real.
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    monkeypatch.setattr(coordinator.client, "_ack_timeout", 0.2)
    fake_server.scripted_responses["03"] = [None]
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert _typed(fake_server) == "4"
    assert coordinator.program_mode is ProgramMode.DOUBT
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_a_key_refused_after_an_acknowledged_prefix_keeps_the_doubt(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.scripted_responses["03"] = ["00", "02"]
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert coordinator.program_mode is ProgramMode.DOUBT
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_the_first_key_refused_by_the_module_returns_to_closed(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.scripted_responses["03"] = ["02"]
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert coordinator.program_mode is ProgramMode.CLOSED
    assert _issue(hass, entry) is None
    await unload_entry(hass, entry)


async def test_an_installer_on_an_older_doubt_leaves_that_doubt_when_nothing_is_sent(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    await _installer_send(hass, entry, "9")
    generation = coordinator._mode.generation
    await coordinator.async_release_session()
    with pytest.raises(HomeAssistantError):
        await _installer_send(hass, entry, "*99")
    assert coordinator.program_mode is ProgramMode.DOUBT
    assert coordinator._mode.generation == generation
    assert _issue(hass, entry) is not None
    await coordinator.async_resume_session()
    await unload_entry(hass, entry)


# -- L4: the doubt save's read-back checks what was saved --------------------


async def test_a_newer_record_in_the_store_is_not_a_failed_doubt_save(
    hass, fake_server
) -> None:
    # A transition during the save writes a newer state over the doubt; the
    # doubt was saved, and the store holds what followed it.
    entry = await _setup(hass, fake_server)
    original = Store.async_save
    newer = {"written": False}

    async def save_then_newer(self, data):
        await original(self, data)
        if isinstance(data, dict) and data.get("mode") == "doubt":
            if not newer["written"]:
                newer["written"] = True
                await original(self, {**data, "revision": int(data["revision"]) + 1})

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Store, "async_save", save_then_newer)
        await _program_key_a(hass, entry)
    assert newer["written"]
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)


async def test_a_session_boundary_during_the_doubt_save_stops_the_entry_as_lost(
    hass, fake_server
) -> None:
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    saving = asyncio.Event()
    release = asyncio.Event()
    original = Store.async_save

    async def hold_doubt(self, data):
        if (
            isinstance(data, dict)
            and data.get("mode") == "doubt"
            and not saving.is_set()
        ):
            saving.set()
            await release.wait()
        await original(self, data)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(Store, "async_save", hold_doubt)
        operation = asyncio.create_task(_program_key_a(hass, entry))
        await asyncio.wait_for(saving.wait(), timeout=1)
        coordinator._transition(ModeEvent.DISCONNECT)
        release.set()
        with pytest.raises(HomeAssistantError) as raised:
            await operation
    # The save was fine; what stopped the entry is the session boundary.
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


# -- L3: wording --------------------------------------------------------------


def test_the_wordings_say_what_is_true_and_what_to_do() -> None:
    en = _en()
    abort = en["issues"]["program_mode_unknown"]["fix_flow"]["abort"]
    assert "Reopen the current repair" not in abort["stale_repair"]
    assert "already" in abort["already_settled"]
    held = abort["operation_in_progress"]
    assert "A programming operation" not in held
    assert "arm" in held and "bypass" in held
    exceptions = en["exceptions"]
    assert "opened by something else" not in exceptions["program_mode_lost"]["message"]
    description = en["issues"]["program_mode_unknown"]["description"]
    assert "went out" not in description
    assert "may have" in description
