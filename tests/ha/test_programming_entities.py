"""The programming entities on the panel device.

Everything here runs against the fake TPI server, so an assertion about a
keystroke is an assertion about what the panel would have received, and an
assertion that nothing was sent is an assertion that the panel heard nothing.

The device page and the actions are two front ends onto the same three guided
operations, so the keystroke sequences asserted here are deliberately the same
strings as in test_field_programming_services.py: a value set on an entity has
to reach the panel exactly as the same value passed to the action does.
"""

from __future__ import annotations

import asyncio

import pytest
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.envisalink_field_programmer.client import (
    EnvisalinkClient,
    TPICommandError,
)
from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import setup_entry, unload_entry


async def _setup(hass, fake_server, *, panel_model: str = "vista_21ip", installer_code="4112"):
    return await setup_entry(
        hass,
        fake_server,
        panel_model=panel_model,
        options={"installer_code": installer_code} if installer_code else {},
    )


def _entity_id(hass, entry, domain: str, suffix: str) -> str:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{suffix}")
    assert entity_id is not None, f"no entity registered for {suffix!r}"
    return entity_id


def _find(hass, entry, domain: str, suffix: str) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id(domain, DOMAIN, f"{entry.entry_id}_{suffix}")


def _sent(fake_server) -> str:
    """Every keystroke character the panel has been sent so far."""
    return "".join(data.split(",", 1)[1] for code, data in fake_server.received if code == "03")


async def _set_number(hass, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )


async def _select(hass, entity_id: str, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": option}, blocking=True
    )


async def _switch(hass, entity_id: str, on: bool) -> None:
    await hass.services.async_call(
        "switch", "turn_on" if on else "turn_off", {"entity_id": entity_id}, blocking=True
    )


async def _press(hass, entity_id: str) -> None:
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)


async def _fill_zone_form(hass, entry, *, zone: int = 3, zone_type: str = "type_03") -> None:
    await _set_number(hass, _entity_id(hass, entry, "number", "program_zone_number"), zone)
    await _select(hass, _entity_id(hass, entry, "select", "program_zone_type"), zone_type)
    await _select(hass, _entity_id(hass, entry, "select", "program_zone_partition"), "partition_1")


async def test_every_field_of_the_guided_actions_is_an_entity(hass, fake_server):
    entry = await _setup(hass, fake_server)
    for domain, suffix in (
        ("number", "program_zone_number"),
        ("number", "program_timing_value"),
        ("select", "program_zone_type"),
        ("select", "program_zone_partition"),
        ("select", "program_zone_hardwire_type"),
        ("select", "program_zone_response_time"),
        ("select", "program_timing_field"),
        ("select", "program_function_key_letter"),
        ("select", "program_function_key_action"),
        ("select", "program_function_key_partition"),
        ("switch", "program_zone_report_enabled"),
        ("switch", "program_confirm"),
        ("switch", "program_confirm_life_safety"),
        ("button", "program_zone"),
        ("button", "set_system_timing"),
        ("button", "program_function_key"),
        ("sensor", "last_programming_result"),
    ):
        entity_id = _entity_id(hass, entry, domain, suffix)
        assert hass.states.get(entity_id) is not None

    # Residential timing is system-wide, so there is no partition to pick, and
    # the 21iP is the one model built from its own guide, so there is nothing
    # to acknowledge.
    assert _find(hass, entry, "select", "program_timing_partition") is None
    assert _find(hass, entry, "switch", "program_confirm_unverified_model") is None

    # Every one of them is a configuration entity except the result, which
    # reports rather than configures.
    registry = er.async_get(hass)
    for domain, suffix in (
        ("number", "program_zone_number"),
        ("select", "program_zone_type"),
        ("switch", "program_confirm"),
        ("button", "program_zone"),
    ):
        assert (
            registry.async_get(_entity_id(hass, entry, domain, suffix)).entity_category == "config"
        )
    result = registry.async_get(_entity_id(hass, entry, "sensor", "last_programming_result"))
    assert result.entity_category == "diagnostic"
    await unload_entry(hass, entry)


async def test_setting_a_field_sends_nothing_to_the_panel(hass, fake_server):
    # The whole point of the form: filling it in is not programming. Nothing
    # reaches the panel until a button is pressed.
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry, zone=7, zone_type="type_09")
    await _select(
        hass, _entity_id(hass, entry, "select", "program_zone_hardwire_type"), "normally_closed"
    )
    await _select(hass, _entity_id(hass, entry, "select", "program_zone_response_time"), "ms_10")
    await _switch(hass, _entity_id(hass, entry, "switch", "program_zone_report_enabled"), False)
    await _set_number(hass, _entity_id(hass, entry, "number", "program_timing_value"), 45)
    await _select(hass, _entity_id(hass, entry, "select", "program_timing_field"), "field_35")
    await _select(hass, _entity_id(hass, entry, "select", "program_function_key_letter"), "key_b")
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == ""

    # And the values are what the entities now report.
    assert hass.states.get(_entity_id(hass, entry, "number", "program_zone_number")).state == "7.0"
    assert (
        hass.states.get(_entity_id(hass, entry, "select", "program_zone_type")).state == "type_09"
    )
    assert hass.states.get(_entity_id(hass, entry, "switch", "program_confirm")).state == "on"
    await unload_entry(hass, entry)


async def test_a_button_refuses_while_the_confirm_switch_is_off(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry)
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert raised.value.translation_key == "confirm_switch_off"
    assert raised.value.translation_placeholders == {
        "action": "Program zone",
        "switch": "Confirm programming",
    }
    assert _sent(fake_server) == ""
    # Nothing was attempted, so there is no result to report yet.
    assert (
        hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result")).state
        == "unknown"
    )
    await unload_entry(hass, entry)


async def test_a_button_names_the_value_that_is_missing(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await _set_number(hass, _entity_id(hass, entry, "number", "program_zone_number"), 3)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert raised.value.translation_key == "programming_value_unset"
    assert raised.value.translation_placeholders["field"] == "Zone type"
    assert _sent(fake_server) == ""
    # The confirmation was spent on the attempt, and the refusal is on record.
    assert hass.states.get(_entity_id(hass, entry, "switch", "program_confirm")).state == "off"
    result = hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result"))
    assert result.state == "refused"
    assert result.attributes["action"] == "program_zone"
    assert "Zone type" in result.attributes["detail"]
    await unload_entry(hass, entry)


async def test_the_zone_button_sends_what_the_action_sends(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    await asyncio.sleep(0.05)
    # Identical to the program_zone action for the same values: zone 3,
    # Perimeter, partition 1, reporting on, end-of-line, 350 ms.
    assert _sent(fake_server) == "4112800*560*03**03*1*1*0*1*0*00**99"
    result = hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result"))
    assert result.state == "success"
    assert result.attributes["action"] == "program_zone"
    assert result.attributes["detail"] == "Command Accepted"
    await unload_entry(hass, entry)


async def test_the_confirm_switch_turns_itself_off_after_a_write(hass, fake_server):
    # One confirmation authorizes exactly one write: a second press with the
    # switch left alone is refused, and nothing more reaches the panel.
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    await asyncio.sleep(0.05)
    sent_once = _sent(fake_server)
    assert hass.states.get(_entity_id(hass, entry, "switch", "program_confirm")).state == "off"

    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert raised.value.translation_key == "confirm_switch_off"
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == sent_once
    await unload_entry(hass, entry)


async def test_a_life_safety_zone_type_needs_its_own_switch(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry, zone=5, zone_type="type_09")  # Fire
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert raised.value.translation_key == "life_safety_zone_type"
    assert _sent(fake_server) == ""
    assert (
        hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result")).state
        == "refused"
    )

    # Both switches on: the same press now goes through.
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm_life_safety"), True)
    await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == "4112800*560*05**09*1*1*0*1*0*00**99"
    # And that confirmation is spent too.
    assert (
        hass.states.get(_entity_id(hass, entry, "switch", "program_confirm_life_safety")).state
        == "off"
    )
    await unload_entry(hass, entry)


async def test_the_timing_button_sends_what_the_action_sends(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await _select(hass, _entity_id(hass, entry, "select", "program_timing_field"), "field_35")
    await _set_number(hass, _entity_id(hass, entry, "number", "program_timing_value"), 45)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await _press(hass, _entity_id(hass, entry, "button", "set_system_timing"))
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == "4112800*3545**99"
    assert (
        hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result")).state
        == "success"
    )
    await unload_entry(hass, entry)


async def test_a_timing_value_the_field_cannot_take_is_refused(hass, fake_server):
    # The number entity's bounds are the widest any field takes; what a
    # particular field accepts is narrower, and the dialect's builder is what
    # knows. 97-99 are extended-time codes on entry delay but not on auto-stay.
    entry = await _setup(hass, fake_server)
    await _select(hass, _entity_id(hass, entry, "select", "program_timing_field"), "field_84")
    await _set_number(hass, _entity_id(hass, entry, "number", "program_timing_value"), 99)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "set_system_timing"))
    assert raised.value.translation_key == "invalid_timing_value"
    assert _sent(fake_server) == ""
    result = hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result"))
    assert result.state == "refused"
    assert result.attributes["action"] == "set_system_timing"
    await unload_entry(hass, entry)


async def test_the_function_key_button_sends_what_the_action_sends(hass, fake_server):
    entry = await _setup(hass, fake_server)
    await _select(hass, _entity_id(hass, entry, "select", "program_function_key_letter"), "key_a")
    await _select(
        hass, _entity_id(hass, entry, "select", "program_function_key_action"), "arm_away"
    )
    await _select(
        hass, _entity_id(hass, entry, "select", "program_function_key_partition"), "partition_1"
    )
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await _press(hass, _entity_id(hass, entry, "button", "program_function_key"))
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == "4112800*571*1*03*0*00*99"
    await unload_entry(hass, entry)


async def test_a_press_with_no_installer_code_is_refused(hass, fake_server):
    entry = await _setup(hass, fake_server, installer_code=None)
    await _fill_zone_form(hass, entry)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert raised.value.translation_key == "no_installer_code"
    assert _sent(fake_server) == ""
    await unload_entry(hass, entry)


async def test_a_refused_command_is_reported_as_a_failure(hass, fake_server, monkeypatch):
    # The sequence was sent and the module rejected it, so what reached the
    # panel is unknown: a device error, not a validation error, and the result
    # sensor says failed rather than refused.
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)

    async def _refuse(self, partition, keys):
        raise TPICommandError("Unknown Command")

    monkeypatch.setattr(EnvisalinkClient, "send_keystrokes", _refuse)
    with pytest.raises(HomeAssistantError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert not isinstance(raised.value, ServiceValidationError)
    result = hass.states.get(_entity_id(hass, entry, "sensor", "last_programming_result"))
    assert result.state == "failed"
    assert "Unknown Command" in result.attributes["detail"]
    assert hass.states.get(_entity_id(hass, entry, "switch", "program_confirm")).state == "off"
    await unload_entry(hass, entry)


async def test_a_dsc_entry_has_no_programming_entities(hass, fake_server):
    # DSC drives none of the guided operations, so the device page offers no
    # form for them rather than buttons that always refuse.
    entry = await _setup(hass, fake_server, panel_model="dsc_pc1864")
    for domain, suffix in (
        ("number", "program_zone_number"),
        ("number", "program_timing_value"),
        ("select", "program_zone_type"),
        ("select", "program_timing_field"),
        ("switch", "program_confirm"),
        ("button", "program_zone"),
        ("button", "set_system_timing"),
        ("button", "program_function_key"),
        ("sensor", "last_programming_result"),
    ):
        assert _find(hass, entry, domain, suffix) is None
    await unload_entry(hass, entry)


async def test_a_commercial_entry_offers_only_the_timing_form(hass, fake_server):
    # The commercial dialect drives timing and nothing else, its timing fields
    # are partition-specific, and the model is not verified against its own
    # guide -- so the partition picker and the acknowledgment switch are there,
    # and the zone and function-key entities are not.
    entry = await _setup(hass, fake_server, panel_model="vista_128bp")
    assert _find(hass, entry, "button", "program_zone") is None
    assert _find(hass, entry, "button", "program_function_key") is None
    assert _find(hass, entry, "select", "program_zone_type") is None
    assert _entity_id(hass, entry, "select", "program_timing_partition")
    assert _entity_id(hass, entry, "switch", "program_confirm_unverified_model")

    await _select(hass, _entity_id(hass, entry, "select", "program_timing_field"), "field_10")
    await _set_number(hass, _entity_id(hass, entry, "number", "program_timing_value"), 4)
    await _select(
        hass, _entity_id(hass, entry, "select", "program_timing_partition"), "partition_1"
    )
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)

    # Unacknowledged: an unverified model refuses before anything is sent.
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "set_system_timing"))
    assert raised.value.translation_key == "unverified_model"
    assert _sent(fake_server) == ""

    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm"), True)
    await _switch(hass, _entity_id(hass, entry, "switch", "program_confirm_unverified_model"), True)
    await _press(hass, _entity_id(hass, entry, "button", "set_system_timing"))
    await asyncio.sleep(0.05)
    # Identical to the set_system_timing action for the same values.
    assert _sent(fake_server) == "41128000*911*1004*99"
    await unload_entry(hass, entry)


async def test_a_refusal_follows_the_user_s_own_entity_names(hass, fake_server):
    """The message names the switch and button as the user sees them, renames included."""
    entry = await _setup(hass, fake_server)
    await _fill_zone_form(hass, entry)
    registry = er.async_get(hass)
    registry.async_update_entity(
        _entity_id(hass, entry, "switch", "program_confirm"), name="Armed for programming"
    )
    registry.async_update_entity(
        _entity_id(hass, entry, "button", "program_zone"), name="Write the zone"
    )
    await hass.async_block_till_done()
    with pytest.raises(ServiceValidationError) as raised:
        await _press(hass, _entity_id(hass, entry, "button", "program_zone"))
    assert raised.value.translation_placeholders == {
        "action": "Write the zone",
        "switch": "Armed for programming",
    }
    await unload_entry(hass, entry)
