"""What the panel and the integration are left with when a guided operation fails.

Each test drives one failure through the fake TPI server and then checks two
things: what reached the panel, and what the next keystroke writer is allowed
to do while Program Mode may still be open.
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.envisalink_field_programmer import field_programming_services
from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import setup_entry, unload_entry

COMPLETE = "4112800*57A*1*03*0**99"


async def _setup(hass, fake_server, **overrides):
    return await setup_entry(
        hass,
        fake_server,
        options={"installer_code": "4112"},
        num_zones=2,
        user_code="1234",
        **overrides,
    )


def _typed(fake_server) -> str:
    return "".join(d.split(",", 1)[1] for c, d in fake_server.received if c == "03")


def _issue(hass, entry):
    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"program_mode_unknown_{entry.entry_id}"
    )


def _entity_id(hass, domain: str, entry, suffix: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.entry_id}_{suffix}"
    )
    assert entity_id is not None
    return entity_id


async def _program_key_a(hass, entry, partition: int = 1) -> None:
    await hass.services.async_call(
        DOMAIN,
        "program_function_key",
        {
            "entry_id": entry.entry_id,
            "key": "A",
            "partition": partition,
            "action": 3,
            "confirm": True,
        },
        blocking=True,
    )


async def _until(predicate, tries: int = 300) -> None:
    for _ in range(tries):
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition never held")


async def _leave_in_doubt(hass, fake_server, entry, monkeypatch) -> None:
    """A guided operation whose *99 the panel never reports: Program Mode in doubt."""
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    fake_server.report_exit = False
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert _issue(hass, entry) is not None
    fake_server.report_exit = True


async def _disarm(hass, entry) -> None:
    await hass.services.async_call(
        "alarm_control_panel",
        "alarm_disarm",
        {
            "entity_id": _entity_id(hass, "alarm_control_panel", entry, "partition_1"),
            "code": "1234",
        },
        blocking=True,
    )


async def _arm_away(hass, entry) -> None:
    await hass.services.async_call(
        "alarm_control_panel",
        "alarm_arm_away",
        {
            "entity_id": _entity_id(hass, "alarm_control_panel", entry, "partition_1"),
            "code": "1234",
        },
        blocking=True,
    )


async def _bypass_action(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN,
        "toggle_zone_bypass",
        {"entry_id": entry.entry_id, "zone": 1},
        blocking=True,
    )


async def _bypass_switch(hass, entry) -> None:
    switch_id = _entity_id(hass, "switch", entry, "zone_1_bypass")
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": switch_id}, blocking=True
    )


async def _raw_send(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN,
        "send_keystrokes",
        {"entry_id": entry.entry_id, "partition": 1, "keys": "1"},
        blocking=True,
    )


WRITERS = {
    "disarm": _disarm,
    "arm_away": _arm_away,
    "bypass_action": _bypass_action,
    "bypass_switch": _bypass_switch,
    "send_keystrokes": _raw_send,
}


async def _enable_bypass_switch(hass, entry) -> None:
    registry = er.async_get(hass)
    registry.async_update_entity(
        _entity_id(hass, "switch", entry, "zone_1_bypass"), disabled_by=None
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize("writer", WRITERS)
async def test_no_writer_types_into_a_program_mode_left_in_doubt(
    hass, fake_server, monkeypatch, writer
):
    # The keypad lock ends with the operation; the doubt does not. A key typed
    # now lands in whatever programming field the panel is showing.
    entry = await _setup(hass, fake_server)
    await _enable_bypass_switch(hass, entry)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch)
    before = _typed(fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await WRITERS[writer](hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == before
    await unload_entry(hass, entry)


@pytest.mark.parametrize("writer", WRITERS)
async def test_no_writer_types_into_a_program_mode_opened_at_the_keypad(
    hass, fake_server, writer
):
    entry = await _setup(hass, fake_server)
    await _enable_bypass_switch(hass, entry)
    await fake_server.enter_program_mode()
    await _until(lambda: entry.runtime_data.data.system.installers_mode)
    with pytest.raises(ServiceValidationError) as raised:
        await WRITERS[writer](hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_the_writers_type_again_once_the_doubt_is_settled(
    hass, fake_server, monkeypatch
):
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch)
    await fake_server.push("03", "1628" + "01" + "000")
    await _until(lambda: _issue(hass, entry) is None)
    before = _typed(fake_server)
    await _disarm(hass, entry)
    assert _typed(fake_server) == before + "12341"
    await unload_entry(hass, entry)


async def test_an_installer_can_still_send_keys_by_hand_into_program_mode(
    hass, fake_server, monkeypatch
):
    # The acknowledged raw send is the remote way out: *99 typed by hand.
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch)
    before = _typed(fake_server)
    fake_server.in_program_mode = True
    await hass.services.async_call(
        DOMAIN,
        "send_keystrokes",
        {
            "entry_id": entry.entry_id,
            "partition": 1,
            "keys": "*99",
            "confirm_installer_risk": True,
        },
        blocking=True,
    )
    assert _typed(fake_server) == before + "*99"
    await _until(lambda: _issue(hass, entry) is None)
    await unload_entry(hass, entry)


async def test_the_doubt_survives_a_reload(hass, fake_server, monkeypatch):
    # An options save reloads the entry and starts a fresh coordinator.
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    before = _typed(fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    with pytest.raises(ServiceValidationError):
        await _disarm(hass, entry)
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == before
    await unload_entry(hass, entry)


async def test_the_module_dropping_the_session_part_way_stops_the_operation(
    hass, fake_server, monkeypatch
):
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_BACKOFF_MIN",
        0.05,
    )
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.drop_on = "4112800*57"
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert not isinstance(raised.value, ServiceValidationError)
    assert _typed(fake_server) == "4112800*57"
    assert _issue(hass, entry) is not None
    fake_server.drop_on = None
    await _until(
        lambda: fake_server.connections == 2 and coordinator.data.system.connected
    )
    # The panel sits in the *57 menu; nothing may type into it from the new session.
    with pytest.raises(ServiceValidationError):
        await _program_key_a(hass, entry)
    with pytest.raises(ServiceValidationError):
        await _disarm(hass, entry)
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == "4112800*57"
    # Neither lock outlived the dropped session.
    await asyncio.wait_for(coordinator.client.keep_alive(), 2)
    await unload_entry(hass, entry)


async def test_a_key_whose_ack_never_comes_stops_the_operation(
    hass, fake_server, monkeypatch
):
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    monkeypatch.setattr(coordinator.client, "_ack_timeout", 0.2)
    # The panel takes the 7 of *57, but the module's ack for it is held back.
    fake_server.scripted_responses["03"] = ["00"] * 9 + [None]
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "keystrokes_not_accepted"
    # Nothing more went out: the panel was left in the *57 menu.
    assert _typed(fake_server) == "4112800*57"
    assert _issue(hass, entry) is not None
    # The lost ack turns up late; the next command waits it out and then goes.
    keepalive = hass.async_create_task(coordinator.client.keep_alive())
    await asyncio.sleep(0.05)
    assert not keepalive.done()
    await fake_server.release_held_acks()
    await asyncio.wait_for(keepalive, 2)
    await unload_entry(hass, entry)


@pytest.mark.parametrize("stage", ["entry_wait", "body"])
async def test_a_cancelled_operation_leaves_the_repair_and_frees_the_locks(
    hass, fake_server, stage
):
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    if stage == "entry_wait":
        fake_server.program_mode_entry = None
        call = hass.async_create_task(_program_key_a(hass, entry))
        await _until(lambda: _typed(fake_server) == "4112800")
    else:
        # The *57's 7 is with the module, its ack not yet back.
        fake_server.scripted_responses["03"] = ["00"] * 9 + [None]
        call = hass.async_create_task(_program_key_a(hass, entry))
        await _until(lambda: _typed(fake_server) == "4112800*57")
    await asyncio.sleep(0.05)
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert _issue(hass, entry) is not None
    await fake_server.release_held_acks()
    # Neither the keypad nor the command lock is left held.
    await asyncio.wait_for(coordinator.client.keep_alive(), 2)
    async with asyncio.timeout(2):
        async with coordinator.client.keypad():
            pass
    await unload_entry(hass, entry)


async def test_a_late_627_after_a_completed_operation_pauses_programming(
    hass, fake_server
):
    entry = await _setup(hass, fake_server)
    await _program_key_a(hass, entry)
    assert _issue(hass, entry) is None
    await fake_server.push("03", "1627" + "01" + "000")
    await _until(lambda: entry.runtime_data.data.system.installers_mode)
    with pytest.raises(ServiceValidationError):
        await _program_key_a(hass, entry)
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)


async def test_duplicated_reports_do_not_change_the_outcome(hass, fake_server):
    entry = await _setup(hass, fake_server)
    fake_server.extra_reports = {
        "4112800": "1627" + "01" + "000",
        "4112800*57A": "1627" + "01" + "000",
    }
    await _program_key_a(hass, entry)
    await fake_server.push("03", "1628" + "01" + "000")
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == COMPLETE
    assert _issue(hass, entry) is None
    assert not entry.runtime_data.data.system.installers_mode
    await unload_entry(hass, entry)


async def test_writers_queued_behind_a_failing_operation_are_refused(
    hass, fake_server, monkeypatch
):
    # They queue while nothing is in doubt; the check that counts is the one
    # made when each gets the keypad, after the operation has failed.
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup(hass, fake_server)
    fake_server.program_mode_entry = None
    fake_server.report_exit = False
    first = hass.async_create_task(_program_key_a(hass, entry))
    await _until(lambda: _typed(fake_server) == "4112800")
    assert _issue(hass, entry) is None
    disarm = hass.async_create_task(_disarm(hass, entry))
    second = hass.async_create_task(_program_key_a(hass, entry))
    await asyncio.sleep(0.05)
    await fake_server.enter_program_mode()
    with pytest.raises(HomeAssistantError) as raised:
        await first
    assert raised.value.translation_key == "program_mode_exit_not_confirmed"
    for queued in (disarm, second):
        with pytest.raises(ServiceValidationError) as raised:
            await queued
        assert raised.value.translation_key == "program_mode_not_closed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)
