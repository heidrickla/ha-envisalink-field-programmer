"""Config flow for Envisalink Field Programmer."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .client import EnvisalinkClient, TPIAuthError, TPIConnectionError
from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_KEEPALIVE_INTERVAL,
    CONF_NUM_PARTITIONS,
    CONF_NUM_ZONES,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USER_CODE,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_NUM_PARTITIONS,
    DEFAULT_NUM_ZONES,
    DEFAULT_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_USER_CODE, default=""): str,
        vol.Required(CONF_NUM_PARTITIONS, default=DEFAULT_NUM_PARTITIONS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=8)
        ),
        vol.Required(CONF_NUM_ZONES, default=DEFAULT_NUM_ZONES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=64)
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


class VistaConsoleConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Envisalink Field Programmer."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._async_abort_entries_match(
                {CONF_HOST: user_input[CONF_HOST], CONF_PORT: user_input[CONF_PORT]}
            )
            try:
                await _test_connection(
                    user_input[CONF_HOST],
                    user_input[CONF_PORT],
                    user_input[CONF_PASSWORD],
                )
            except TPIAuthError:
                errors["base"] = "invalid_auth"
            except TPIConnectionError:
                errors["base"] = "cannot_connect"
            except OSError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error validating Envisalink Field Programmer connection")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Envisalink Field Programmer ({user_input[CONF_HOST]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> VistaConsoleOptionsFlow:
        return VistaConsoleOptionsFlow(config_entry)


class VistaConsoleOptionsFlow(OptionsFlow):
    """Adjust keepalive interval and default user code after setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        data = self._config_entry.data
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_USER_CODE,
                    default=options.get(CONF_USER_CODE, data.get(CONF_USER_CODE, "")),
                ): str,
                vol.Optional(
                    CONF_INSTALLER_CODE,
                    default=options.get(
                        CONF_INSTALLER_CODE, data.get(CONF_INSTALLER_CODE, "")
                    ),
                ): str,
                vol.Optional(
                    CONF_KEEPALIVE_INTERVAL,
                    default=options.get(
                        CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=10, max=300)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
