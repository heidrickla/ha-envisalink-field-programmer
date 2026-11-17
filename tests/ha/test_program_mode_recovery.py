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
from custom_components.envisalink_field_programmer.client import (
    TPICommandError,
    TPIConnectionError,
)
from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.models import ProgramMode

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


async def _leave_in_doubt(
    hass, fake_server, entry, monkeypatch, kind: str = "no_628"
) -> None:
    """A guided operation that leaves Program Mode in doubt.

    no_628: the panel reported 627, then never reported the exit after *99.
    no_627: the panel never reported anything, so only the doubt holds writers.
    """
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    if kind == "no_628":
        fake_server.report_exit = False
    else:
        fake_server.program_mode_entry = None
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert _issue(hass, entry) is not None
    fake_server.report_exit = True
    fake_server.program_mode_entry = "4112800"


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


async def _enable_bypass_switch(hass, fake_server, entry) -> None:
    registry = er.async_get(hass)
    registry.async_update_entity(
        _entity_id(hass, "switch", entry, "zone_1_bypass"), disabled_by=None
    )
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    await fake_server.push("00", "1,1008,0,00,READY")
    await _until(lambda: 1 in entry.runtime_data._fresh_partitions)


@pytest.mark.parametrize("kind", ["no_628", "no_627"])
@pytest.mark.parametrize("writer", WRITERS)
async def test_no_writer_types_into_a_program_mode_left_in_doubt(
    hass, fake_server, monkeypatch, writer, kind
):
    # The keypad lock ends with the operation; the doubt does not. A key typed
    # now lands in whatever programming field the panel is showing.
    entry = await _setup(hass, fake_server)
    await _enable_bypass_switch(hass, fake_server, entry)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, kind)
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
    await _enable_bypass_switch(hass, fake_server, entry)
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
    # The open report belonged to the dropped session.
    assert coordinator.data.system.program_mode is ProgramMode.DOUBT
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
    async with asyncio.timeout(2):
        async with coordinator.client.keypad():
            pass
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


async def test_a_second_627_invalidates_the_operation_s_menu(hass, fake_server):
    entry = await _setup(hass, fake_server)
    fake_server.extra_reports = {
        "4112800": "1627" + "01" + "000",
        "4112800*57A": "1627" + "01" + "000",
    }
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == "4112800"
    assert _issue(hass, entry) is not None
    await fake_server.push("03", "1628" + "01" + "000")
    await _until(lambda: _issue(hass, entry) is None)
    await unload_entry(hass, entry)


async def test_writers_queued_behind_a_failing_operation_are_refused(
    hass, fake_server, monkeypatch
):
    # They queue while Program Mode is closed, the first operation holding the
    # keypad but not yet written; the check that counts is the one made when
    # each gets the keypad, after the operation has failed.
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup(hass, fake_server)
    command_lock = entry.runtime_data.client._command_lock
    await command_lock.acquire()
    fake_server.report_exit = False
    first = hass.async_create_task(_program_key_a(hass, entry))
    await asyncio.sleep(0.05)
    disarm = hass.async_create_task(_disarm(hass, entry))
    second = hass.async_create_task(_program_key_a(hass, entry))
    await asyncio.sleep(0.05)
    assert _issue(hass, entry) is None
    assert _typed(fake_server) == ""
    command_lock.release()
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


async def _program_zone_2(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": 3,
            "zone_type": 3,
            "partition": 2,
            "confirm": True,
        },
        blocking=True,
    )


async def _commercial_timing_on_2(hass, entry) -> None:
    # Commercial timing is per partition: *09 to *12 take the partition first.
    await hass.services.async_call(
        DOMAIN,
        "set_system_timing",
        {
            "entry_id": entry.entry_id,
            "field": "09",
            "value": 4,
            "partition": 2,
            "confirm": True,
            "confirm_unverified_model": True,
        },
        blocking=True,
    )


# Each full sequence carries partition 2 at its prompt: after the zone type in
# *56, after the key letter in *57, and as the first digit of commercial *09.
GUIDED_ON_PARTITION_2 = {
    "program_function_key": (
        "vista_21ip",
        lambda hass, entry: _program_key_a(hass, entry, 2),
        "4112800*57A*2*03*0**99",
    ),
    "program_zone": (
        "vista_21ip",
        _program_zone_2,
        "4112800*560*03**03*2*1*0*1*0*00**99",
    ),
    "set_system_timing": (
        "vista_128bp",
        _commercial_timing_on_2,
        "41128000*912*0904*99",
    ),
}


@pytest.mark.parametrize("op", GUIDED_ON_PARTITION_2)
async def test_a_guided_operation_programs_another_partition_from_the_entry_s_keypad(
    hass, fake_server, op
):
    # The partition at the *56 or *57 PARTITION prompt is data; Program Mode is
    # opened and typed on the entry's keypad, partition 1.
    model, call, expected = GUIDED_ON_PARTITION_2[op]
    entry = await _setup(hass, fake_server, panel_model=model)
    fake_server.program_mode_entry = expected[: expected.index("*")]
    await call(hass, entry)
    assert _typed(fake_server) == expected
    assert {d.split(",", 1)[0] for c, d in fake_server.received if c == "03"} == {"1"}
    assert _issue(hass, entry) is None
    await unload_entry(hass, entry)


async def _raw_send_on_2(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN,
        "send_keystrokes",
        {
            "entry_id": entry.entry_id,
            "partition": 2,
            "keys": "1",
            "confirm_installer_risk": True,
        },
        blocking=True,
    )


async def _disarm_2(hass, entry) -> None:
    await entry.runtime_data.async_disarm(2, "1234")


UNTRACKED_PARTITION_WRITERS = {
    "send_keystrokes": _raw_send_on_2,
    "disarm": _disarm_2,
}


@pytest.mark.parametrize("writer", UNTRACKED_PARTITION_WRITERS)
async def test_a_partition_the_entry_does_not_track_gets_nothing(
    hass, fake_server, writer
):
    # Nothing reports a partition above the entry's count, so its arm state
    # and its keypad are unknown here.
    entry = await _setup(hass, fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await UNTRACKED_PARTITION_WRITERS[writer](hass, entry)
    assert raised.value.translation_key == "partition_not_configured"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == ""
    assert _issue(hass, entry) is None
    await unload_entry(hass, entry)


async def test_a_confirmed_raw_send_leaves_program_mode_in_doubt(hass, fake_server):
    # It may have opened Program Mode, and the panel's 627 can come late or
    # never: a disarm right after it must not be typed into a field.
    entry = await _setup(hass, fake_server)
    fake_server.program_mode_entry = None
    await hass.services.async_call(
        DOMAIN,
        "send_keystrokes",
        {
            "entry_id": entry.entry_id,
            "partition": 1,
            "keys": "4112800",
            "confirm_installer_risk": True,
        },
        blocking=True,
    )
    with pytest.raises(ServiceValidationError) as raised:
        await _disarm(hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    assert _typed(fake_server) == "4112800"
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_a_program_mode_reported_open_survives_a_reload(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await fake_server.enter_program_mode()
    await _until(lambda: entry.runtime_data.data.system.installers_mode)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as raised:
        await _disarm(hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_an_armed_report_settles_the_doubt(hass, fake_server, monkeypatch):
    # A Vista cannot arm with Program Mode open, so an armed partition is the
    # panel saying Program Mode is closed.
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, "no_627")
    before = _typed(fake_server)
    # Icon LEDs: armed away (bit 2) and AC present (bit 3).
    await fake_server.push("00", "1,000C,0,00,ARMED AWAY")
    await _until(lambda: entry.runtime_data.data.partition(1).armed)
    await _disarm(hass, entry)
    assert _typed(fake_server) == before + "12341"
    assert _issue(hass, entry) is None
    await unload_entry(hass, entry)


async def test_a_627_after_an_armed_report_holds_writers_again(
    hass, fake_server, monkeypatch
):
    # The latest report wins: the armed report settles the doubt, and a 627
    # that follows it records open.
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, "no_627")
    await fake_server.push("00", "1,000C,0,00,ARMED AWAY")
    await _until(lambda: _issue(hass, entry) is None)
    assert entry.runtime_data.data.system.program_mode is ProgramMode.CLOSED
    before = _typed(fake_server)
    await fake_server.push("03", "1627" + "01" + "000")
    await _until(lambda: _issue(hass, entry) is not None)
    with pytest.raises(ServiceValidationError):
        await _disarm(hass, entry)
    assert _typed(fake_server) == before
    await unload_entry(hass, entry)


async def test_a_session_closed_for_a_missing_ack_logs_no_error(
    hass, fake_server, monkeypatch
):
    # The owed ack is failed when its session goes; nothing may log that as
    # an unhandled error.
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.coordinator.RECONNECT_BACKOFF_MIN",
        0.05,
    )
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    monkeypatch.setattr(coordinator.client, "_ack_timeout", 0.2)
    fake_server.scripted_responses["00"] = [None]
    with pytest.raises(TPICommandError):
        await coordinator.client.keep_alive()
    with pytest.raises(TPIConnectionError):
        await coordinator.client.keep_alive()
    await _until(
        lambda: fake_server.connections == 2 and coordinator.data.system.connected
    )
    await _disarm(hass, entry)
    assert _typed(fake_server) == "12341"
    await unload_entry(hass, entry)
