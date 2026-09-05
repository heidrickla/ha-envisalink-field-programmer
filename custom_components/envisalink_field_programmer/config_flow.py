"""Config flow for Envisalink Field Programmer: setup, reauth and options."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from .client import EnvisalinkClient, TPIAuthError, TPIError
from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_KEEPALIVE_INTERVAL,
    CONF_MAC,
    CONF_NUM_PARTITIONS,
    CONF_NUM_ZONES,
    CONF_PANEL_MODEL,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_REMOVE_INSTALLER_CODE,
    CONF_REMOVE_USER_CODE,
    CONF_USER_CODE,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_NUM_PARTITIONS,
    DEFAULT_NUM_ZONES,
    DEFAULT_PANEL_MODEL,
    DEFAULT_PORT,
    DOMAIN,
    PROBE_SETTLE_DELAY,
)
from .coordinator import VistaConsoleCoordinator
from .panels import get_model, model_choices

_LOGGER = logging.getLogger(__name__)

_PASSWORD = selector.TextSelector(
    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
)
# Both alarm codes are secrets too: they arm, disarm and open Program Mode.
_SECRETS = {CONF_PASSWORD, CONF_USER_CODE, CONF_INSTALLER_CODE}

# Zones/partitions ranges here are the widest any supported panel allows; the
# actual per-model maximum is enforced against the selected model after submit
# (see async_step_user), so the form can stay a single step.
STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Required(CONF_PASSWORD): _PASSWORD,
        vol.Required(CONF_PANEL_MODEL, default=DEFAULT_PANEL_MODEL): vol.In(model_choices()),
        vol.Optional(CONF_USER_CODE, default=""): _PASSWORD,
        vol.Required(CONF_NUM_PARTITIONS, default=DEFAULT_NUM_PARTITIONS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=8)
        ),
        vol.Required(CONF_NUM_ZONES, default=DEFAULT_NUM_ZONES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=250)
        ),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): _PASSWORD})

# The reconfigure form is the connection half of the setup form. The password
# is optional here: blank keeps the stored one, since it is never sent back to
# the browser. The default user code stays in the options, where it is set.
STEP_RECONFIGURE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): cv.port,
        vol.Optional(CONF_PASSWORD): _PASSWORD,
        vol.Required(CONF_PANEL_MODEL, default=DEFAULT_PANEL_MODEL): vol.In(model_choices()),
        vol.Required(CONF_NUM_PARTITIONS, default=DEFAULT_NUM_PARTITIONS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=8)
        ),
        vol.Required(CONF_NUM_ZONES, default=DEFAULT_NUM_ZONES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=250)
        ),
    }
)


async def _test_connection(host: str, port: int, password: str) -> None:
    """Attempt a login handshake, then leave the module's session properly free.

    Raises TPIAuthError / TPIConnectionError / OSError on failure.

    The Envisalink admits one TPI client at a time and frees that slot only
    once it has seen the connection close. ``disconnect()`` waits for the
    close to land; the settle on top of it is the module's own reaction time,
    measured on 2026-09-05 as longer than the 4 ms it took setup to open the
    next connection and be dropped mid-login.
    """

    # The probe logs in and leaves, so anything the panel volunteers is dropped.
    client = EnvisalinkClient(host, port, password, event_callback=lambda _event: None)
    try:
        await client.connect()
    finally:
        await client.disconnect()
        await asyncio.sleep(PROBE_SETTLE_DELAY)


async def _async_try(host: str, port: int, password: str) -> dict[str, str]:
    """Validate against the Envisalink. Returns the form errors, empty on success."""
    try:
        await _test_connection(host, port, password)
    except TPIAuthError:
        return {"base": "invalid_auth"}
    except (TPIError, OSError):
        return {"base": "cannot_connect"}
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Unexpected error validating the Envisalink connection")
        return {"base": "unknown"}
    return {}


def _capacity_errors(user_input: Mapping[str, Any]) -> dict[str, str]:
    """Form errors for counts the selected panel model cannot have."""
    model = get_model(user_input[CONF_PANEL_MODEL])
    errors: dict[str, str] = {}
    if user_input[CONF_NUM_ZONES] > model.max_zones:
        errors[CONF_NUM_ZONES] = "too_many_zones"
    if user_input[CONF_NUM_PARTITIONS] > model.max_partitions:
        errors[CONF_NUM_PARTITIONS] = "too_many_partitions"
    return errors


def _without_secrets(values: Mapping[str, Any]) -> dict[str, Any]:
    """What may go back to the browser as a suggested value after an error."""
    return {k: v for k, v in values.items() if k not in _SECRETS}


class VistaConsoleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup, discovery, reauth and reconfigure for one Envisalink."""

    VERSION = 1

    def __init__(self) -> None:
        # Filled in by a DHCP discovery: what to suggest on the form and the
        # MAC to store with the entry so a later move can be recognised.
        self._discovered: dict[str, Any] = {}
        self._discovered_mac: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
            )
            errors = _capacity_errors(user_input)
            if not errors:
                errors = await _async_try(
                    user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_PASSWORD]
                )
            if not errors:
                await self.async_set_unique_id(f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}")
                self._abort_if_unique_id_configured()
                data = dict(user_input)
                if self._discovered_mac is not None:
                    data[CONF_MAC] = self._discovered_mac
                return self.async_create_entry(
                    title=f"Envisalink Field Programmer ({user_input[CONF_HOST]})",
                    data=data,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, _without_secrets(user_input or self._discovered)
            ),
            errors=errors,
        )

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """An Envisacor-made device took a DHCP lease.

        The MAC prefix 00:1C:2A belongs to Envisacor Technologies, who make
        the Envisalink, so the device is worth offering. TPI itself exposes no
        identity, so the MAC learned here is what lets a later lease at a new
        address be recognised as the same unit rather than a second one.
        """
        host = discovery_info.ip
        mac = format_mac(discovery_info.macaddress)

        for entry in self._async_current_entries(include_ignore=False):
            stored_mac = entry.data.get(CONF_MAC)
            if stored_mac == mac:
                if entry.data.get(CONF_HOST) != host:
                    port = entry.data[CONF_PORT]
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={**entry.data, CONF_HOST: host},
                        unique_id=f"{host}:{port}",
                        title=f"Envisalink Field Programmer ({host})",
                    )
                    self._reload_unless_the_entry_reloads_itself(entry)
                return self.async_abort(reason="already_configured")
            if stored_mac is None and entry.data.get(CONF_HOST) == host:
                # An entry added by hand at this address: learn its MAC so the
                # next lease elsewhere is recognised as a move.
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_MAC: mac}
                )
                return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(f"{host}:{DEFAULT_PORT}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})
        self._discovered = {CONF_HOST: host}
        self._discovered_mac = mac
        self.context["title_placeholders"] = {"host": host}
        return await self.async_step_user()

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The Envisalink rejected the stored password; ask for a new one."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await _async_try(
                entry.data[CONF_HOST], entry.data[CONF_PORT], user_input[CONF_PASSWORD]
            )
            if not errors:
                self.hass.config_entries.async_update_entry(
                    entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
                self._reload_unless_the_entry_reloads_itself(entry)
                return self.async_abort(reason="reauth_successful")
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            description_placeholders={"host": entry.data[CONF_HOST]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the address, password, panel model or the zone and partition counts.

        The unique id is the address itself, because the TPI protocol exposes
        no serial or MAC to identify the unit by. A moved Envisalink therefore
        gets a new unique id rather than failing a mismatch check; what is
        refused is an address another entry already holds.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host: str = user_input[CONF_HOST]
            port: int = user_input[CONF_PORT]
            # Blank keeps the stored password; it is never sent to the browser.
            password: str = user_input.get(CONF_PASSWORD) or entry.data[CONF_PASSWORD]
            errors = _capacity_errors(user_input)
            if not errors and self._address_owned_by_another_entry(entry, host, port):
                return self.async_abort(reason="already_configured")
            probed = not errors and self._connection_changed(entry, user_input)
            if probed:
                errors = await self._async_try_borrowing_the_session(entry, host, port, password)
            if not errors:
                updated = self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, **user_input, CONF_PASSWORD: password},
                    unique_id=f"{host}:{port}",
                    title=f"Envisalink Field Programmer ({host})",
                )
                self._reload_unless_the_entry_reloads_itself(entry)
                if probed and not updated:
                    # The form was submitted with the settings the entry
                    # already had, so nothing reloads it and nothing else
                    # would give the borrowed session back.
                    await self._async_give_the_session_back(entry)
                return self.async_abort(reason="reconfigure_successful")

        current = user_input if user_input is not None else entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_SCHEMA, _without_secrets(current)
            ),
            errors=errors,
        )

    @staticmethod
    def _connection_changed(entry: ConfigEntry, user_input: Mapping[str, Any]) -> bool:
        """Whether the reconfigure form changed anything a probe could test.

        Host, port and password are the whole of what a login proves. When
        none of them moved -- the usual reconfigure, which changes a count or
        the panel model -- there is nothing to test, and probing anyway would
        take the module's single TPI session away from the running
        coordinator for no reason.
        """
        if user_input.get(CONF_PASSWORD):
            return True
        # Every value is named with its type first: both mappings are
        # Mapping[str, Any], and a comparison with an Any operand is itself
        # Any, which mypy --strict will not let a function declared to return
        # bool return.
        host: str = user_input[CONF_HOST]
        port: int = user_input[CONF_PORT]
        current_host: str = entry.data[CONF_HOST]
        current_port: int = entry.data[CONF_PORT]
        return host != current_host or port != current_port

    async def _async_try_borrowing_the_session(
        self, entry: ConfigEntry, host: str, port: int, password: str
    ) -> dict[str, str]:
        """Probe the Envisalink, borrowing the session a loaded entry holds.

        The module admits one TPI client at a time, so on a loaded entry the
        probe can only get in if the coordinator lets go first: without this
        the reconfigure form answered "cannot connect" every time, measured
        against the hardware on 2026-09-05. A successful reconfigure reloads
        the entry, which connects afresh; a failed one puts the session back
        here, because the entry is staying exactly as it was.
        """
        coordinator = self._running_coordinator(entry)
        if coordinator is None:
            return await _async_try(host, port, password)
        await coordinator.async_release_session()
        errors = await _async_try(host, port, password)
        if errors:
            await coordinator.async_resume_session()
        return errors

    async def _async_give_the_session_back(self, entry: ConfigEntry) -> None:
        """Reconnect a coordinator whose entry is not going to be reloaded."""
        coordinator = self._running_coordinator(entry)
        if coordinator is not None:
            await coordinator.async_resume_session()

    @staticmethod
    def _running_coordinator(entry: ConfigEntry) -> VistaConsoleCoordinator | None:
        """The coordinator holding this entry's TPI session, if it has one."""
        if entry.state is not ConfigEntryState.LOADED:
            return None
        coordinator: VistaConsoleCoordinator = entry.runtime_data
        return coordinator

    def _reload_unless_the_entry_reloads_itself(self, entry: ConfigEntry) -> None:
        """Reload an entry that has nothing else to reload it.

        A loaded entry carries the update listener registered at setup, and
        Home Assistant wants that listener to be the one scheduling the
        reload. An entry that is not loaded, which is the usual state during
        a reauth or after the Envisalink has moved, has no listener, so
        nothing would pick the new settings up.
        """
        if not entry.update_listeners:
            self.hass.config_entries.async_schedule_reload(entry.entry_id)

    def _address_owned_by_another_entry(self, entry: ConfigEntry, host: str, port: int) -> bool:
        """Whether some other entry already talks to this host and port."""
        return any(
            other.entry_id != entry.entry_id
            and other.data.get(CONF_HOST) == host
            and other.data.get(CONF_PORT) == port
            for other in self._async_current_entries(include_ignore=False)
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VistaConsoleOptionsFlow:
        return VistaConsoleOptionsFlow()


class VistaConsoleOptionsFlow(OptionsFlow):
    """Adjust the default user code, installer code and keepalive interval.

    The stored codes never go back to the browser, so the code fields are
    shown empty: a blank field keeps the stored code, the remove switches
    clear it.
    """

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        options = self.config_entry.options
        data = self.config_entry.data
        stored_user_code: str = options.get(CONF_USER_CODE, data.get(CONF_USER_CODE, ""))
        stored_installer_code: str = options.get(CONF_INSTALLER_CODE, "")

        if user_input is not None:
            user_code = (
                ""
                if user_input[CONF_REMOVE_USER_CODE]
                else (user_input.get(CONF_USER_CODE) or stored_user_code)
            )
            installer_code = (
                ""
                if user_input[CONF_REMOVE_INSTALLER_CODE]
                else (user_input.get(CONF_INSTALLER_CODE) or stored_installer_code)
            )
            return self.async_create_entry(
                title="",
                data={
                    **options,
                    CONF_USER_CODE: user_code,
                    CONF_INSTALLER_CODE: installer_code,
                    CONF_KEEPALIVE_INTERVAL: user_input[CONF_KEEPALIVE_INTERVAL],
                },
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_USER_CODE, default=""): _PASSWORD,
                vol.Optional(CONF_REMOVE_USER_CODE, default=False): bool,
                vol.Optional(CONF_INSTALLER_CODE, default=""): _PASSWORD,
                vol.Optional(CONF_REMOVE_INSTALLER_CODE, default=False): bool,
                vol.Required(
                    CONF_KEEPALIVE_INTERVAL,
                    default=options.get(CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )
        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            description_placeholders={
                "user_code_state": "set" if stored_user_code else "not set",
                "installer_code_state": "set" if stored_installer_code else "not set",
            },
        )
