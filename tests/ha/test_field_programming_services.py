"""End-to-end tests for the guided field-programming services.

Verifies the services are wired correctly (schema validation, the confirm/
confirm_life_safety gates, and that the exact expected keystroke sequence
reaches the panel) against a real fake TPI server, not mocks.
"""

from __future__ import annotations

import asyncio

import pytest
import voluptuous as vol
from homeassistant.core import Context
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)

from custom_components.envisalink_field_programmer import field_programming_services
from custom_components.envisalink_field_programmer.client import (
    EnvisalinkClient,
    TPICommandError,
)
from custom_components.envisalink_field_programmer.const import DOMAIN

from .conftest import setup_entry, unload_entry


async def _household_member(hass):
    """A signed-in user in the ordinary users group, as a household account is.

    The first person account is the owner, and the owner is an administrator.
    """
    if not any(u.is_owner for u in await hass.auth.async_get_users()):
        await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("Household", group_ids=["system-users"])
    assert not user.is_admin
    return user


async def _setup_entry(
    hass,
    fake_server,
    *,
    installer_code: str | None = "4112",
    panel_model: str = "vista_21ip",
):
    return await setup_entry(
        hass,
        fake_server,
        panel_model=panel_model,
        options={"installer_code": installer_code} if installer_code else {},
    )


async def _unload(hass, entry):
    await unload_entry(hass, entry)


async def test_send_keystrokes_guards_dsc_installer_mode_by_dialect(hass, fake_server):
    # Security regression: send_keystrokes must guard against the *selected
    # panel's* installer-mode trigger. On a DSC entry, *8<code> opens installer
    # programming and must be refused without confirm_installer_risk -- it would
    # slip through if the service defaulted to the VISTA 800 rule (the bug this
    # test locks down).
    entry = await _setup_entry(hass, fake_server, panel_model="dsc_pc1864")
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN,
            "send_keystrokes",
            {"entry_id": entry.entry_id, "partition": 1, "keys": "*84112500"},
            blocking=True,
        )
    assert raised.value.translation_key == "opens_program_mode"
    await _unload(hass, entry)


async def test_program_zone_sends_expected_keystrokes(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": 3,
            "zone_type": 3,  # Perimeter, not life-safety
            "partition": 1,
            "confirm": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "03"]
    full_sent = "".join(
        d.split(",", 1)[1] for d in keystroke_frames
    )  # strip partition prefix
    # 4112800 (enter Program Mode) + *56 zone menu: confirm=no, zone 03,
    # accept summary, type=03 (Perimeter), partition=1, report=on,
    # hardwire=EOL(default), response=350ms(default), alpha=no, exit zone
    # menu, then *99 (exit Program Mode).
    assert full_sent == "4112800*560*03**03*1*1*0*1*0*00**99"
    await _unload(hass, entry)


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("send_keystrokes", {"partition": 1, "keys": "1"}),
        (
            "program_zone",
            {"zone_number": 3, "zone_type": 3, "partition": 1, "confirm": True},
        ),
        (
            "set_system_timing",
            {"field": "10", "value": 4, "partition": 1, "confirm": True},
        ),
        (
            "program_function_key",
            {"key": "A", "partition": 1, "action": 3, "confirm": True},
        ),
    ],
)
async def test_a_panel_action_is_refused_to_a_user_who_is_not_an_administrator(
    hass, fake_server, service, data
):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"entry_id": entry.entry_id, **data},
            blocking=True,
            context=Context(user_id=(await _household_member(hass)).id),
        )
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == ""
    await _unload(hass, entry)


async def test_zone_bypass_stays_open_to_every_user(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "toggle_zone_bypass",
        {"entry_id": entry.entry_id, "zone": 2},
        blocking=True,
        context=Context(user_id=(await _household_member(hass)).id),
    )
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == "*102#"
    await _unload(hass, entry)


def _sent(fake_server) -> str:
    return "".join(
        data.split(",", 1)[1] for code, data in fake_server.received if code == "03"
    )


async def _program_zone(hass, entry, zone: int, **extra) -> None:
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": zone,
            "zone_type": 3,
            "partition": 1,
            "confirm": True,
            **extra,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)


async def test_zones_9_to_16_are_refused_until_zone_doubling_is_stated(
    hass, fake_server
):
    entry = await _setup_entry(hass, fake_server)
    for zone in (9, 12, 16):
        with pytest.raises(ServiceValidationError) as raised:
            await _program_zone(hass, entry, zone, zone_connection="wired_expander")
        assert raised.value.translation_key == "zone_doubling_not_stated"
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == ""
    await _unload(hass, entry)


async def test_a_doubled_zone_is_programmed_without_wiring_prompts(hass, fake_server):
    entry = await setup_entry(
        hass,
        fake_server,
        panel_model="vista_21ip",
        options={"installer_code": "4112", "zone_doubling": "on"},
    )
    await _program_zone(hass, entry, 12)
    # Zone type, partition and report code, then PROGRAM ALPHA: the panel
    # skips wiring, response time and input type for a doubled zone.
    assert _sent(fake_server) == "4112800*560*12**03*1*1*0*00**99"

    with pytest.raises(ServiceValidationError) as raised:
        await _program_zone(hass, entry, 9, zone_connection="wired_expander")
    assert raised.value.translation_key == "zone_unavailable_with_doubling"
    await _unload(hass, entry)


async def test_an_expansion_zone_is_sent_only_with_its_connection_stated(
    hass, fake_server
):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_zone(hass, entry, 20)
    assert raised.value.translation_key == "zone_connection_unset"
    with pytest.raises(ServiceValidationError) as raised:
        await _program_zone(hass, entry, 20, zone_connection="wireless")
    assert raised.value.translation_key == "zone_is_wireless"
    await asyncio.sleep(0.05)
    assert _sent(fake_server) == ""

    await _program_zone(hass, entry, 20, zone_connection="wired_expander")
    assert _sent(fake_server) == "4112800*560*20**03*1*1*2*0*00**99"
    await _unload(hass, entry)


async def test_button_zones_are_refused(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_zone(hass, entry, 49)
    assert raised.value.translation_key == "zone_is_button"
    assert _sent(fake_server) == ""
    await _unload(hass, entry)


async def test_zone_doubling_wiring_needs_doubling_stated_on(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_zone(hass, entry, 5, hardwire_type="3")
    assert raised.value.translation_key == "hardwire_zone_doubling_off"
    assert _sent(fake_server) == ""
    await _unload(hass, entry)


async def test_a_vista_15p_zone_has_no_partition_prompt(hass, fake_server):
    entry = await _setup_entry(hass, fake_server, panel_model="vista_15p")
    await _program_zone(hass, entry, 3)
    assert _sent(fake_server) == "4112800*560*03**03*1*0*1*0*00**99"
    with pytest.raises(ServiceValidationError) as raised:
        await _program_zone(hass, entry, 7)
    assert raised.value.translation_key == "zone_not_on_panel"
    assert "1-6, 9-34, 49-56" in str(raised.value)
    await _unload(hass, entry)


async def test_a_vista_10p_zone_1_gets_its_wiring_prompt(hass, fake_server):
    entry = await _setup_entry(hass, fake_server, panel_model="vista_10p")
    await _program_zone(hass, entry, 1)
    assert _sent(fake_server) == "4112800*560*01**03*1*0*1*0*00**99"
    await _unload(hass, entry)


async def test_program_zone_requires_confirm(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 3,
                "zone_type": 3,
                "partition": 1,
                "confirm": False,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_program_zone_fire_type_requires_life_safety_confirm(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(ServiceValidationError) as raised:
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 5,
                "zone_type": 9,  # Fire
                "partition": 1,
                "confirm": True,
                "confirm_life_safety": False,
            },
            blocking=True,
        )
    assert raised.value.translation_key == "life_safety_zone_type"
    assert raised.value.translation_placeholders == {
        "zone_type": "9",
        "label": "Fire (smoke/heat detector)",
        "switch": "Confirm life-safety zone type",
    }
    await _unload(hass, entry)


async def test_program_zone_fire_type_succeeds_when_confirmed(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "program_zone",
        {
            "entry_id": entry.entry_id,
            "zone_number": 5,
            "zone_type": 9,
            "partition": 1,
            "confirm": True,
            "confirm_life_safety": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "03"]
    assert keystroke_frames  # something was sent
    await _unload(hass, entry)


async def test_program_zone_requires_installer_code_configured(hass, fake_server):
    entry = await _setup_entry(hass, fake_server, installer_code=None)
    with pytest.raises(ServiceValidationError, match="installer code"):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 3,
                "zone_type": 3,
                "partition": 1,
                "confirm": True,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_guided_programming_refused_for_dsc(hass, fake_server):
    # DSC PowerSeries uses positional whole-section programming, not the
    # VISTA *56 per-zone menu, so the guided service refuses outright rather
    # than building meaningless (and potentially destructive) keystrokes.
    entry = await _setup_entry(hass, fake_server, panel_model="dsc_pc1864")
    with pytest.raises(ServiceValidationError, match="not available"):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 3,
                "zone_type": 3,
                "partition": 1,
                "confirm": True,
                "confirm_unverified_model": True,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_zone_programming_refused_for_commercial_vista(hass, fake_server):
    # The commercial VISTA-128BP supports guided timing but not zone
    # programming (its #93 zone menu is not driven), so program_zone is refused.
    entry = await _setup_entry(hass, fake_server, panel_model="vista_128bp")
    with pytest.raises(ServiceValidationError, match="not available"):
        await hass.services.async_call(
            DOMAIN,
            "program_zone",
            {
                "entry_id": entry.entry_id,
                "zone_number": 3,
                "zone_type": 3,
                "partition": 1,
                "confirm": True,
                "confirm_unverified_model": True,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_commercial_vista_timing_sends_expected_keystrokes(hass, fake_server):
    # Commercial timing IS supported: set Exit Delay #1 (*10) = 4 units (60s) on
    # partition 1. Requires confirm_unverified_model (128BP is provisional).
    entry = await _setup_entry(hass, fake_server, panel_model="vista_128bp")
    fake_server.program_mode_entry = "41128000"
    await hass.services.async_call(
        DOMAIN,
        "set_system_timing",
        {
            "entry_id": entry.entry_id,
            "field": "10",
            "value": 4,
            "partition": 1,
            "confirm": True,
            "confirm_unverified_model": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    frames = [d for c, d in fake_server.received if c == "03"]
    full = "".join(d.split(",", 1)[1] for d in frames)
    # <code>8000 (commercial entry) + *91<p> (select partition) + *10<vv> + *99
    assert full == "41128000*911*1004*99"
    await _unload(hass, entry)


async def test_commercial_vista_timing_rejects_residential_field(hass, fake_server):
    # Residential field number 34 is not valid on a commercial panel.
    entry = await _setup_entry(hass, fake_server, panel_model="vista_128bp")
    with pytest.raises(ServiceValidationError, match="not valid"):
        await hass.services.async_call(
            DOMAIN,
            "set_system_timing",
            {
                "entry_id": entry.entry_id,
                "field": "34",
                "value": 45,
                "confirm": True,
                "confirm_unverified_model": True,
            },
            blocking=True,
        )
    await _unload(hass, entry)


async def test_set_system_timing_sends_expected_keystrokes(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "set_system_timing",
        {
            "entry_id": entry.entry_id,
            "field": "34",
            "value": 45,
            "confirm": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "03"]
    full_sent = "".join(d.split(",", 1)[1] for d in keystroke_frames)
    assert full_sent == "4112800*3445**99"
    await _unload(hass, entry)


async def test_set_system_timing_rejects_value_out_of_range(hass, fake_server):
    # The value range depends on the field and dialect, so the schema cannot
    # check it. An out-of-range value is the caller's mistake and must surface
    # as a validation error, not the builder's raw ValueError with a traceback.
    entry = await _setup_entry(hass, fake_server)
    with pytest.raises(ServiceValidationError, match="EXIT_DELAY"):
        await hass.services.async_call(
            DOMAIN,
            "set_system_timing",
            {
                "entry_id": entry.entry_id,
                "field": "34",
                "value": 999,
                "confirm": True,
            },
            blocking=True,
        )
    keystroke_frames = [d for c, d in fake_server.received if c == "03"]
    assert not keystroke_frames  # nothing reached the panel
    await _unload(hass, entry)


async def test_guided_action_reports_device_refusal_as_device_error(
    hass, fake_server, monkeypatch
):
    # A refused or unacknowledged command is a device failure, not bad input:
    # HomeAssistantError, and not the ServiceValidationError subclass. The
    # fake server always acknowledges, so the client is made to refuse here.
    entry = await _setup_entry(hass, fake_server)

    async def _refuse(self, partition, key, guard=None):
        raise TPICommandError("Unknown Command")

    monkeypatch.setattr(EnvisalinkClient, "send_keypress", _refuse)
    with pytest.raises(HomeAssistantError, match="Unknown Command") as excinfo:
        await hass.services.async_call(
            DOMAIN,
            "program_function_key",
            {
                "entry_id": entry.entry_id,
                "key": "A",
                "partition": 1,
                "action": 3,
                "confirm": True,
            },
            blocking=True,
        )
    assert not isinstance(excinfo.value, ServiceValidationError)
    await _unload(hass, entry)


async def test_program_function_key_sends_expected_keystrokes(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await hass.services.async_call(
        DOMAIN,
        "program_function_key",
        {
            "entry_id": entry.entry_id,
            "key": "A",
            "partition": 1,
            "action": 3,  # Arm Away
            "confirm": True,
        },
        blocking=True,
    )
    await asyncio.sleep(0.05)
    keystroke_frames = [d for c, d in fake_server.received if c == "03"]
    full_sent = "".join(d.split(",", 1)[1] for d in keystroke_frames)
    assert full_sent == "4112800*57A*1*03*0**99"
    await _unload(hass, entry)


async def test_send_keystrokes_never_sends_a_function_key_letter(hass, fake_server):
    # Over the TPI a bare A-D is that key's emergency; only the guided *57
    # operation may send one, even with confirm_installer_risk.
    entry = await _setup_entry(hass, fake_server)
    for keys in ("A", "4112800*57A*1*03*0**99"):
        with pytest.raises(ServiceValidationError) as raised:
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
        assert raised.value.translation_key == "invalid_keystroke_characters"
    await asyncio.sleep(0.05)
    assert not [d for c, d in fake_server.received if c == "03"]
    await _unload(hass, entry)


def _typed(fake_server) -> str:
    return "".join(d.split(",", 1)[1] for c, d in fake_server.received if c == "03")


async def _program_key_a(hass, entry) -> None:
    await hass.services.async_call(
        DOMAIN,
        "program_function_key",
        {
            "entry_id": entry.entry_id,
            "key": "A",
            "partition": 1,
            "action": 3,
            "confirm": True,
        },
        blocking=True,
    )


async def test_nothing_follows_the_entry_until_the_panel_reports_program_mode(
    hass, fake_server
):
    # Over the TPI a bare A is that key's emergency, so the *57A must not go
    # out until the panel itself says Program Mode is open (CID 627).
    entry = await _setup_entry(hass, fake_server)
    fake_server.program_mode_entry = None
    call = hass.async_create_task(_program_key_a(hass, entry))
    for _ in range(100):
        if _typed(fake_server) == "4112800":
            break
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.2)
    assert _typed(fake_server) == "4112800"
    assert not call.done()
    await fake_server.enter_program_mode()
    await call
    assert _typed(fake_server) == "4112800*57A*1*03*0**99"
    await _unload(hass, entry)


async def test_a_silent_panel_gets_nothing_after_the_entry(
    hass, fake_server, monkeypatch
):
    # A wrong installer code, an armed panel or a *98 lockout leaves the panel
    # in normal mode: no CID 627 arrives, and the sequence stops at 800.
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup_entry(hass, fake_server)
    fake_server.program_mode_entry = None
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert not isinstance(raised.value, ServiceValidationError)
    assert raised.value.translation_key == "program_mode_not_confirmed"
    await asyncio.sleep(0.2)
    assert _typed(fake_server) == "4112800"
    # The panel may have opened Program Mode without reporting it: the next
    # attempt is refused before anything is sent, until the doubt is settled.
    assert _issue(hass, entry) is not None
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == "4112800"
    await _unload(hass, entry)


@pytest.mark.parametrize("flag", ["armed", "exit_delay"])
async def test_an_armed_or_arming_partition_is_refused_before_anything_is_sent(
    hass, fake_server, flag
):
    entry = await _setup_entry(hass, fake_server)
    setattr(entry.runtime_data.data.partition(1), flag, True)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "partition_armed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == ""
    await _unload(hass, entry)


async def test_a_panel_already_in_program_mode_is_refused_before_anything_is_sent(
    hass, fake_server
):
    # Keys typed into an open Program Mode land in whatever field is showing.
    entry = await _setup_entry(hass, fake_server)
    await fake_server.enter_program_mode()
    for _ in range(100):
        if entry.runtime_data.data.system.installers_mode:
            break
        await asyncio.sleep(0.01)
    with pytest.raises(ServiceValidationError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_not_closed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == ""
    # A 628 the panel never sent would hold this forever: the repair gives the
    # user's word at the keypad the same weight.
    assert _issue(hass, entry) is not None
    fake_server.in_program_mode = False  # the user pressed *99 at the keypad
    await _confirm_repair(hass, entry)
    assert not entry.runtime_data.data.system.installers_mode
    await _program_key_a(hass, entry)
    assert _typed(fake_server) == "4112800*57A*1*03*0**99"
    await _unload(hass, entry)


async def test_two_operations_take_turns_in_program_mode(hass, fake_server):
    # The second waits for the first to exit with *99 rather than typing its
    # entry into the first one's Program Mode.
    entry = await _setup_entry(hass, fake_server)
    await asyncio.gather(_program_key_a(hass, entry), _program_key_a(hass, entry))
    assert _typed(fake_server) == "4112800*57A*1*03*0**99" * 2
    await _unload(hass, entry)


def _issue(hass, entry):
    from homeassistant.helpers import issue_registry as ir

    return ir.async_get(hass).async_get_issue(
        DOMAIN, f"program_mode_unknown_{entry.entry_id}"
    )


async def _confirm_repair(hass, entry) -> None:
    from homeassistant.components.repairs import repairs_flow_manager
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "repairs", {})
    manager = repairs_flow_manager(hass)
    flow = await manager.async_init(
        DOMAIN, data={"issue_id": f"program_mode_unknown_{entry.entry_id}"}
    )
    assert flow["step_id"] == "confirm"
    result = await manager.async_configure(flow["flow_id"], {})
    assert result["type"] == "create_entry"
    assert _issue(hass, entry) is None


async def test_a_627_followed_at_once_by_628_sends_nothing_more(
    hass, fake_server, monkeypatch
):
    # The entry's report is only good while it is the panel's latest word: a
    # 628 read in the same batch means normal mode, where A is the emergency.
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup_entry(hass, fake_server)
    fake_server.extra_reports = {"4112800": "1628" + "01" + "000"}
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_not_confirmed"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == "4112800"
    # Both reports came after the entry, and the latest says closed.
    assert _issue(hass, entry) is None
    await _unload(hass, entry)


async def test_program_mode_closing_part_way_stops_the_next_key(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    fake_server.extra_reports = {"4112800*57": "1628" + "01" + "000"}
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_lost"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == "4112800*57"
    # The panel reported Program Mode closed after the entry: no doubt is left.
    assert _issue(hass, entry) is None
    await _unload(hass, entry)


async def test_a_reconnect_after_the_entry_sends_nothing_more(hass, fake_server):
    # Keys after the entry belong to the session the entry went out on.
    entry = await _setup_entry(hass, fake_server)
    fake_server.program_mode_entry = None
    call = hass.async_create_task(_program_key_a(hass, entry))
    for _ in range(100):
        if _typed(fake_server) == "4112800":
            break
        await asyncio.sleep(0.01)
    entry.runtime_data.session_generation += 1
    await fake_server.enter_program_mode()
    with pytest.raises(HomeAssistantError) as raised:
        await call
    assert raised.value.translation_key == "program_mode_lost"
    assert _typed(fake_server) == "4112800"
    await _unload(hass, entry)


async def test_a_disconnect_starts_a_new_session(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    coordinator = entry.runtime_data
    before = coordinator.session_generation
    await fake_server.stop()
    for _ in range(200):
        if coordinator.session_generation != before:
            break
        await asyncio.sleep(0.01)
    assert coordinator.session_generation == before + 1
    await _unload(hass, entry)


async def test_a_missing_exit_report_is_an_error_and_a_repair(
    hass, fake_server, monkeypatch
):
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup_entry(hass, fake_server)
    fake_server.report_exit = False
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_exit_not_confirmed"
    assert _typed(fake_server) == "4112800*57A*1*03*0**99"
    assert _issue(hass, entry) is not None
    await _unload(hass, entry)


async def test_a_clean_operation_leaves_no_repair(hass, fake_server):
    entry = await _setup_entry(hass, fake_server)
    await _program_key_a(hass, entry)
    assert _issue(hass, entry) is None
    assert not entry.runtime_data.data.system.installers_mode
    await _unload(hass, entry)


async def test_other_keystrokes_wait_for_a_sequence_in_program_mode(hass, fake_server):
    # A raw send (or an arm, disarm or bypass) typed between the entry and
    # *99 would land in a programming field: it waits for the keypad.
    entry = await _setup_entry(hass, fake_server)
    fake_server.program_mode_entry = None
    call = hass.async_create_task(_program_key_a(hass, entry))
    for _ in range(100):
        if _typed(fake_server) == "4112800":
            break
        await asyncio.sleep(0.01)
    raw = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "send_keystrokes",
            {"entry_id": entry.entry_id, "partition": 1, "keys": "1"},
            blocking=True,
        )
    )
    await asyncio.sleep(0.2)
    assert _typed(fake_server) == "4112800"
    await fake_server.enter_program_mode()
    await call
    await raw
    assert _typed(fake_server) == "4112800*57A*1*03*0**99" + "1"
    await _unload(hass, entry)


async def test_the_panel_reporting_the_exit_clears_the_repair(
    hass, fake_server, monkeypatch
):
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup_entry(hass, fake_server)
    fake_server.program_mode_entry = None
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert _issue(hass, entry) is not None
    await fake_server.enter_program_mode()
    await fake_server.push("03", "1628" + "01" + "000")
    for _ in range(100):
        if _issue(hass, entry) is None:
            break
        await asyncio.sleep(0.01)
    assert _issue(hass, entry) is None
    await _unload(hass, entry)


async def test_an_exit_report_clears_the_repair_without_a_state_change(
    hass, fake_server, monkeypatch
):
    # The 627 was never seen, so the coordinator never believed Program Mode
    # open; the panel's 628 after *99 at the keypad still settles the doubt.
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup_entry(hass, fake_server)
    fake_server.program_mode_entry = None
    with pytest.raises(HomeAssistantError):
        await _program_key_a(hass, entry)
    assert _issue(hass, entry) is not None
    assert not entry.runtime_data.data.system.installers_mode
    await fake_server.push("03", "1628" + "01" + "000")
    for _ in range(100):
        if _issue(hass, entry) is None:
            break
        await asyncio.sleep(0.01)
    assert _issue(hass, entry) is None
    fake_server.program_mode_entry = "4112800"
    await _program_key_a(hass, entry)
    assert _typed(fake_server).endswith("4112800*57A*1*03*0**99")
    await _unload(hass, entry)


async def test_an_exit_report_before_the_entry_settles_nothing(
    hass, fake_server, monkeypatch
):
    # Only a 628 after the entry went out says where this operation left the panel.
    monkeypatch.setattr(field_programming_services, "PROGRAM_MODE_REPORT_TIMEOUT", 0.3)
    entry = await _setup_entry(hass, fake_server)
    coordinator = entry.runtime_data
    fake_server.program_mode_entry = None
    await fake_server.push("03", "1628" + "01" + "000")
    for _ in range(100):
        if coordinator.program_mode_exit_reports:
            break
        await asyncio.sleep(0.01)
    assert coordinator.program_mode_exit_reports == 1
    with pytest.raises(HomeAssistantError) as raised:
        await _program_key_a(hass, entry)
    assert raised.value.translation_key == "program_mode_not_confirmed"
    assert _issue(hass, entry) is not None
    await _unload(hass, entry)


@pytest.mark.parametrize(("accepted", "repair"), [(0, False), (1, True), (6, True)])
async def test_an_entry_key_the_module_refuses(hass, fake_server, accepted, repair):
    # The module answers 02 to one key of the entry. Refused first, nothing
    # reached the panel. Refused later, the delivered prefix stays in the
    # panel's input, where the next attempt's keys could complete the entry.
    entry = await _setup_entry(hass, fake_server)
    fake_server.scripted_responses["03"] = ["00"] * accepted + ["02"]
    with pytest.raises(HomeAssistantError, match="rejected"):
        await _program_key_a(hass, entry)
    # Every frame the module received, the refused one included.
    assert _typed(fake_server) == "4112800"[: accepted + 1]
    assert (_issue(hass, entry) is not None) is repair
    await _unload(hass, entry)


async def test_a_body_key_the_module_refuses_leaves_the_repair(hass, fake_server):
    # Once the entry went out, a refusal later on leaves Program Mode open.
    entry = await _setup_entry(hass, fake_server)
    fake_server.scripted_responses["03"] = ["00"] * 8 + ["02"]
    with pytest.raises(HomeAssistantError, match="rejected"):
        await _program_key_a(hass, entry)
    assert _issue(hass, entry) is not None
    await _unload(hass, entry)


async def test_program_mode_closing_while_a_key_waits_to_be_written(
    hass, fake_server, monkeypatch
):
    # The check is made under the command lock, right before the write: a
    # 628 read while the key waited for the lock stops it.
    entry = await _setup_entry(hass, fake_server)
    coordinator = entry.runtime_data
    command_lock = coordinator.client._command_lock
    held = asyncio.Event()
    wait = coordinator.async_wait_for_program_mode

    async def _then_hold_the_lock(is_open, timeout):
        result = await wait(is_open, timeout)
        if is_open:
            await command_lock.acquire()
            held.set()
        return result

    monkeypatch.setattr(coordinator, "async_wait_for_program_mode", _then_hold_the_lock)
    call = hass.async_create_task(_program_key_a(hass, entry))
    await asyncio.wait_for(held.wait(), 5)
    await fake_server.push("03", "1628" + "01" + "000")
    for _ in range(100):
        if not coordinator.data.system.installers_mode:
            break
        await asyncio.sleep(0.01)
    command_lock.release()
    with pytest.raises(HomeAssistantError) as raised:
        await call
    assert raised.value.translation_key == "program_mode_lost"
    await asyncio.sleep(0.1)
    assert _typed(fake_server) == "4112800"
    assert _issue(hass, entry) is None
    await _unload(hass, entry)
