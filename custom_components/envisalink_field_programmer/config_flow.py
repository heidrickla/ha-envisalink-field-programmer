"""Config flow for Envisalink Field Programmer: setup, reauth and options."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .client import EnvisalinkClient, TPIAuthError, TPIError
from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_KEEPALIVE_INTERVAL,
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
)
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
    """Attempt a login handshake and immediately disconnect.

    Raises TPIAuthError / TPIConnectionError / OSError on failure.
    """

    def _noop_event(_event: Any) -> None:
        return None

    client = EnvisalinkClient(host, port, password, event_callback=_noop_event)
    try:
        await client.connect()
    finally:
        await client.disconnect()


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
    """Handle setup and reauth for one Envisalink."""

    VERSION = 1

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
                return self.async_create_entry(
                    title=f"Envisalink Field Programmer ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, _without_secrets(user_input or {})
            ),
            errors=errors,
        )

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
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
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
            if not errors:
                errors = await _async_try(host, port, password)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=f"{host}:{port}",
                    title=f"Envisalink Field Programmer ({host})",
                    data_updates={**user_input, CONF_PASSWORD: password},
                )

        current = user_input if user_input is not None else entry.data
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_SCHEMA, _without_secrets(current)
            ),
            errors=errors,
        )

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
