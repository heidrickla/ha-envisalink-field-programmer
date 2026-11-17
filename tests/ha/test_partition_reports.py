"""A partition's arm state is known only from a report, and the integration asks.

The fake panel answers ^01,<n> (change default partition) with a keypad update
for partition n when it has that partition. Whether a real EnvisaLink does is
unverified, so every refusal here must also say what the user does next.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .conftest import unload_entry
from .test_program_mode_recovery import (
    COMPLETE,
    _disarm,
    _entity_id,
    _program_key_a,
    _setup,
    _typed,
    _until,
)

COORDINATOR = "custom_components.envisalink_field_programmer.coordinator"
TRANSLATIONS = (
    Path(__file__).parent.parent.parent
    / "custom_components"
    / "envisalink_field_programmer"
    / "translations"
    / "en.json"
)


def _fast(monkeypatch, seconds: float = 0.2) -> None:
    monkeypatch.setattr(
        f"{COORDINATOR}.PARTITION_REPORT_TIMEOUT", seconds, raising=False
    )
    monkeypatch.setattr(f"{COORDINATOR}.RECONNECT_BACKOFF_MIN", 0.05)


async def _outage(hass, fake_server, entry) -> None:
    """Drop the session and wait for the reconnect, with the panel's answers as set."""
    coordinator = entry.runtime_data
    fake_server.drop_on = "1"
    with pytest.raises(HomeAssistantError):
        await _disarm(hass, entry)
    await _until(
        lambda: (
            fake_server.connections >= 2
            and coordinator.data.system.connected
            and not fake_server._writer.is_closing()
        )
    )
    fake_server.drop_on = None


async def test_a_partition_nobody_reported_is_asked_for_before_programming(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    fake_server.answer_partition_requests = False
    entry = await _setup(hass, fake_server)
    fake_server.answer_partition_requests = True
    await _program_key_a(hass, entry)
    assert _typed(fake_server) == COMPLETE
    # Asked at setup, where nothing answered, and again when the press needed it.
    assert fake_server.partition_requests.count(1) >= 2
    await unload_entry(hass, entry)


async def test_the_request_leaves_the_module_on_partition_1(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    fake_server.panel_partitions = 1
    entry = await _setup(hass, fake_server, num_partitions=3)
    fake_server.panel_partitions = 3
    fake_server.partition_requests.clear()
    await _program_key_a(hass, entry)
    assert fake_server.partition_requests == [3, 2, 1]
    assert fake_server.default_partition == 1
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)


async def test_a_partition_the_panel_does_not_have_is_refused_for_a_reason_that_can_end(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    fake_server.panel_partitions = 1
    entry = await _setup(hass, fake_server, num_partitions=2)
    started = asyncio.get_running_loop().time()
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert asyncio.get_running_loop().time() - started < 3
    assert raised.value.translation_key == "partition_report_pending"
    assert raised.value.translation_placeholders == {"partition": "2"}
    assert 2 in fake_server.partition_requests
    assert _typed(fake_server) == ""
    # Not permanent: once the panel reports the partition the same press goes.
    fake_server.panel_partitions = 2
    await _program_key_a(hass, entry)
    assert _typed(fake_server) == COMPLETE
    await unload_entry(hass, entry)


async def test_a_silent_partition_is_never_taken_as_disarmed_or_absent(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    fake_server.answer_partition_requests = False
    entry = await _setup(hass, fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "partition_report_pending"
    with pytest.raises(ServiceValidationError) as raised:
        await _disarm(hass, entry)
    assert raised.value.translation_key == "partition_report_pending"
    assert _typed(fake_server) == ""
    # A keypad update that arrives by itself ends the wait.
    await fake_server.push("00", "1,1008,0,00,READY")
    entity_id = _entity_id(hass, "alarm_control_panel", entry, "partition_1")
    await _until(lambda: hass.states.get(entity_id).state == "disarmed")
    await _disarm(hass, entry)
    assert _typed(fake_server) == "12341"
    await unload_entry(hass, entry)


async def test_arm_disarm_and_bypass_need_a_report_after_an_outage(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    entry = await _setup(hass, fake_server)
    fake_server.answer_partition_requests = False
    await _outage(hass, fake_server, entry)
    before = _typed(fake_server)
    for action in ("alarm_disarm", "alarm_arm_away"):
        with pytest.raises(ServiceValidationError) as raised:
            await hass.services.async_call(
                "alarm_control_panel",
                action,
                {
                    "entity_id": _entity_id(
                        hass, "alarm_control_panel", entry, "partition_1"
                    ),
                    "code": "1234",
                },
                blocking=True,
            )
        assert raised.value.translation_key == "partition_report_pending"
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            "envisalink_field_programmer",
            "toggle_zone_bypass",
            {"entry_id": entry.entry_id, "zone": 1},
            blocking=True,
        )
    assert raised.value.translation_key == "partition_report_pending"
    assert _typed(fake_server) == before
    await unload_entry(hass, entry)


async def test_the_outage_report_is_asked_for_and_ends_the_refusal(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    entry = await _setup(hass, fake_server)
    fake_server.partition_requests.clear()
    await _outage(hass, fake_server, entry)
    # The coordinator asked for the report when it reconnected.
    await _until(lambda: 1 in fake_server.partition_requests)
    entity_id = _entity_id(hass, "alarm_control_panel", entry, "partition_1")
    await _until(lambda: hass.states.get(entity_id).state == "disarmed")
    before = _typed(fake_server)
    await _disarm(hass, entry)
    assert _typed(fake_server) == before + "12341"
    await unload_entry(hass, entry)


async def test_a_partition_reads_unknown_until_it_reports(
    hass, fake_server, monkeypatch
) -> None:
    _fast(monkeypatch)
    fake_server.answer_partition_requests = False
    entry = await _setup(hass, fake_server)
    entity_id = _entity_id(hass, "alarm_control_panel", entry, "partition_1")
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"
    await fake_server.push("00", "1,1008,0,00,READY")
    await _until(lambda: hass.states.get(entity_id).state == "disarmed")
    await _outage(hass, fake_server, entry)
    await _until(lambda: hass.states.get(entity_id).state == "unknown")
    await unload_entry(hass, entry)


@pytest.mark.parametrize("how", ["setup", "reconnect", "resume"])
async def test_every_way_of_establishing_a_session_asks_for_the_reports(
    hass, fake_server, monkeypatch, how
) -> None:
    _fast(monkeypatch)
    entry = await _setup(hass, fake_server, num_partitions=2)
    coordinator = entry.runtime_data
    if how == "setup":
        assert set(fake_server.partition_requests) == {1, 2}
    elif how == "reconnect":
        fake_server.partition_requests.clear()
        await _outage(hass, fake_server, entry)
        await _until(lambda: {1, 2} <= set(fake_server.partition_requests))
    else:
        await coordinator.async_release_session()
        fake_server.partition_requests.clear()
        await coordinator.async_resume_session()
        assert {1, 2} <= set(fake_server.partition_requests)
    for number in (1, 2):
        entity_id = _entity_id(
            hass, "alarm_control_panel", entry, f"partition_{number}"
        )
        await _until(lambda eid=entity_id: hass.states.get(eid).state == "disarmed")
    await unload_entry(hass, entry)


async def test_the_disarmed_check_itself_refuses_a_partition_that_has_not_reported(
    hass, fake_server, monkeypatch
) -> None:
    """The check holds on its own, not only through the wait that precedes it."""
    _fast(monkeypatch)
    entry = await _setup(hass, fake_server)
    coordinator = entry.runtime_data
    coordinator.data.partitions[1].fresh = False
    for part_way in (False, True):
        with pytest.raises(ServiceValidationError) as raised:
            coordinator._require_disarmed(part_way=part_way)
        assert raised.value.translation_key == "partition_report_pending"
    coordinator.data.partitions[1].fresh = True
    coordinator._require_disarmed(part_way=False)
    await unload_entry(hass, entry)


def test_the_refusal_names_the_partition_and_says_what_to_do() -> None:
    message = json.loads(TRANSLATIONS.read_text(encoding="utf-8"))["exceptions"][
        "partition_report_pending"
    ]["message"]
    assert "{partition}" in message
    assert "Reconfigure" in message
    assert "try again" in message
