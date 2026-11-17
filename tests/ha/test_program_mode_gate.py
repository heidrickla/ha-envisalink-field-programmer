"""Program Mode is checked at every key's write, against the one stored state.

Each test drives the fake TPI server so a report lands between the moment a
writer takes the keypad and the moment one of its keys is written, or arrives
from somewhere the rule must not trust, and checks what reached the panel.
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import issue_registry as ir

from custom_components.envisalink_field_programmer.client import EnvisalinkClient
from custom_components.envisalink_field_programmer.const import DOMAIN
from custom_components.envisalink_field_programmer.models import ProgramMode

from .conftest import setup_entry, unload_entry
from .test_field_programming_services import _confirm_repair
from .test_program_mode_recovery import (
    COMPLETE,
    _disarm,
    _issue,
    _leave_in_doubt,
    _program_key_a,
    _setup,
    _typed,
    _until,
)

CID_627 = "1627" + "01" + "000"
ARMED_AWAY = "000C,0,00,ARMED AWAY"


async def test_a_disarm_queued_behind_a_command_is_stopped_by_a_627_before_its_turn(
    hass, fake_server
):
    # The disarm takes the keypad while Program Mode is closed, then waits for
    # the command lock; the 627 lands while it waits.
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.scripted_responses["00"] = [None]
    keepalive = asyncio.ensure_future(coordinator.client.keep_alive())
    await _until(lambda: ("00", "") in fake_server.received)
    disarm = asyncio.ensure_future(_disarm(hass, entry))
    await asyncio.sleep(0.05)
    assert not disarm.done()
    await fake_server.push("03", CID_627)
    await _until(lambda: _issue(hass, entry) is not None)
    await fake_server.release_held_acks()
    await keepalive
    with pytest.raises(ServiceValidationError) as raised:
        await disarm
    assert raised.value.translation_key == "program_mode_not_closed"
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_a_627_arriving_with_a_key_s_ack_stops_the_rest_of_the_disarm(
    hass, fake_server
):
    entry = await _setup(hass, fake_server)
    fake_server.extra_reports["12"] = CID_627
    with pytest.raises(HomeAssistantError) as raised:
        await _disarm(hass, entry)
    assert raised.value.translation_key == "program_mode_opened"
    assert _typed(fake_server) == "12"
    assert entry.runtime_data.data.system.program_mode is ProgramMode.OPEN
    await unload_entry(hass, entry)


async def test_a_627_during_the_entry_stops_a_guided_operation(hass, fake_server):
    # The operation's own 627 can only follow its last entry key; one that
    # lands before it is somebody else's Program Mode.
    entry = await _setup(hass, fake_server)
    fake_server.extra_reports["41"] = CID_627
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == "41"
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_a_partition_arming_during_the_entry_stops_a_guided_operation(
    hass, fake_server
):
    # The disarmed check holds at every entry key's write, not only when the
    # keypad is taken.
    entry = await _setup(hass, fake_server)
    fake_server.scripted_responses["03"] = ["00", None]
    operation = asyncio.ensure_future(_program_key_a(hass, entry))
    await _until(lambda: _typed(fake_server) == "41")
    await fake_server.push("00", "1," + ARMED_AWAY)
    await _until(lambda: entry.runtime_data.data.partitions[1].armed)
    await fake_server.release_held_acks()
    with pytest.raises(HomeAssistantError) as raised:
        await operation
    assert raised.value.translation_key == "partition_armed_part_way"
    assert _typed(fake_server) == "41"
    # The operation's own keys raised the doubt; an armed report while it
    # held the keypad does not settle it.
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_an_armed_report_does_not_close_an_open_program_mode(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await fake_server.enter_program_mode()
    await _until(lambda: _issue(hass, entry) is not None)
    await fake_server.push("00", "1," + ARMED_AWAY)
    await _until(lambda: entry.runtime_data.data.partitions[1].armed)
    assert entry.runtime_data.data.system.program_mode is ProgramMode.OPEN
    with pytest.raises(ServiceValidationError):
        await _disarm(hass, entry)
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


@pytest.mark.parametrize("partition", ["2", "9", "x", ""])
async def test_an_armed_report_the_entry_does_not_track_settles_nothing(
    hass, fake_server, monkeypatch, partition
):
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, "no_627")
    before = _typed(fake_server)
    await fake_server.push("00", f"{partition}," + ARMED_AWAY)
    await fake_server.push("00", "1,1008,0,00,READY")
    await _until(lambda: entry.runtime_data.data.partitions[1].ready)
    assert set(entry.runtime_data.data.partitions) == {1}
    with pytest.raises(ServiceValidationError):
        await _disarm(hass, entry)
    assert _typed(fake_server) == before
    assert _issue(hass, entry) is not None
    await unload_entry(hass, entry)


async def test_an_armed_report_mid_operation_neither_stops_it_nor_settles_it(
    hass, fake_server, monkeypatch
):
    # Program Mode is open on the operation's own entry; an armed report then
    # is not the panel closing it, so the operation goes on, and without a 628
    # the doubt stays.
    monkeypatch.setattr(
        "custom_components.envisalink_field_programmer.field_programming_services.PROGRAM_MODE_REPORT_TIMEOUT",
        0.3,
    )
    entry = await _setup(hass, fake_server)
    fake_server.report_exit = False
    held = [None if i == 9 else "00" for i in range(len(COMPLETE))]
    fake_server.scripted_responses["03"] = held
    operation = asyncio.ensure_future(_program_key_a(hass, entry))
    await _until(lambda: len(_typed(fake_server)) == 10)
    await fake_server.push("00", "1," + ARMED_AWAY)
    await _until(lambda: entry.runtime_data.data.partitions[1].armed)
    await fake_server.release_held_acks()
    with pytest.raises(HomeAssistantError) as raised:
        await operation
    assert raised.value.translation_key == "program_mode_exit_not_confirmed"
    assert _typed(fake_server) == COMPLETE
    assert _issue(hass, entry) is not None
    with pytest.raises(ServiceValidationError):
        await _disarm(hass, entry)
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)


async def test_a_repair_confirmed_while_the_entry_sets_up_leaves_no_doubt(
    hass, fake_server, monkeypatch
):
    # The repair flow only tells a loaded entry; Home Assistant deletes the
    # issue either way, and the issue is the one record of the doubt.
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, "no_627")
    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    real_connect = EnvisalinkClient.connect_with_retry

    async def confirm_then_connect(self, delay):
        await _confirm_repair(hass, entry)
        await real_connect(self, delay)

    monkeypatch.setattr(EnvisalinkClient, "connect_with_retry", confirm_then_connect)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    before = _typed(fake_server)
    await _disarm(hass, entry)
    assert _typed(fake_server) == before + "12341"
    assert entry.runtime_data.data.system.program_mode is ProgramMode.CLOSED
    await unload_entry(hass, entry)


async def test_a_deleted_issue_wakes_the_entry_s_state(hass, fake_server, monkeypatch):
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, "no_627")
    ir.async_delete_issue(hass, DOMAIN, f"program_mode_unknown_{entry.entry_id}")
    await hass.async_block_till_done()
    assert entry.runtime_data.data.system.program_mode is ProgramMode.CLOSED
    await unload_entry(hass, entry)


async def test_a_doubt_is_written_to_disk_as_a_repair_a_restart_restores(
    hass, fake_server, monkeypatch
):
    # Home Assistant restores only a persistent issue as an active, fixable
    # repair; any other comes back inactive and cannot be confirmed.
    entry = await _setup(hass, fake_server)
    await _leave_in_doubt(hass, fake_server, entry, monkeypatch, "no_627")
    stored = _issue(hass, entry).to_json()
    assert stored["is_persistent"] is True
    assert stored["is_fixable"] is True
    assert stored["data"] == {"entry_id": entry.entry_id}
    await unload_entry(hass, entry)


async def _program_zone(hass, entry, partition: int) -> None:
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": 3,
            "zone_type": 3,
            "partition": partition,
            "confirm": True,
        },
        blocking=True,
    )


async def _timing(hass, entry, partition: int) -> None:
    await hass.services.async_call(
        DOMAIN,
        "set_system_timing",
        {
            "entry_id": entry.entry_id,
            "field": "34",
            "value": 45,
            "partition": partition,
            "confirm": True,
        },
        blocking=True,
    )


ABOVE_THE_PANEL = {
    "program_zone on a VISTA-15P": ("vista_15p", _program_zone, 2),
    "program_function_key on a VISTA-10P": ("vista_10p", _program_key_a, 3),
    "set_system_timing on a VISTA-15P": ("vista_15p", _timing, 2),
    "set_system_timing on a VISTA-21iP": ("vista_21ip", _timing, 4),
}


@pytest.mark.parametrize("case", ABOVE_THE_PANEL)
async def test_a_partition_the_panel_does_not_have_is_not_programmed(
    hass, fake_server, case
):
    model, call, partition = ABOVE_THE_PANEL[case]
    entry = await setup_entry(
        hass,
        fake_server,
        options={"installer_code": "4112"},
        panel_model=model,
    )
    with pytest.raises(ServiceValidationError) as raised:
        await call(hass, entry, partition)
    assert raised.value.translation_key == "partition_not_on_panel"
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)


async def test_every_tracked_partition_is_checked_before_programming(hass, fake_server):
    entry = await _setup(hass, fake_server, num_partitions=2)
    await fake_server.push("00", "2," + ARMED_AWAY)
    await _until(lambda: entry.runtime_data.data.partitions[2].armed)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "partition_armed"
    assert raised.value.translation_placeholders == {"partition": "2"}
    assert _typed(fake_server) == ""
    await unload_entry(hass, entry)
