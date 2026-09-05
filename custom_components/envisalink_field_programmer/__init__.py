"""The Envisalink Field Programmer integration."""

from __future__ import annotations

import logging

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.typing import ConfigType

from .client import TPIAuthError, TPIError
from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_KEEPALIVE_INTERVAL,
    CONF_NUM_PARTITIONS,
    CONF_NUM_ZONES,
    CONF_PANEL_MODEL,
    CONF_PASSWORD,
    CONF_PORT,
    DEFAULT_KEEPALIVE_INTERVAL,
    DEFAULT_PANEL_MODEL,
    DOMAIN,
    ISSUE_TPI_SESSION_BUSY,
)
from .coordinator import VistaConsoleConfigEntry, VistaConsoleCoordinator
from .field_programming_services import async_register_field_programming_services
from .frontend import async_register_frontend
from .programming import async_register_services

_LOGGER = logging.getLogger(__name__)

# Nothing is configured from YAML; async_setup exists to register the actions,
# and hassfest wants that said explicitly.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions once, at component setup.

    Registered here rather than per entry so a call made while the entry is
    unloaded gets a translated refusal instead of looking like a typo in the
    action name.
    """
    async_register_services(hass)
    async_register_field_programming_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: VistaConsoleConfigEntry) -> bool:
    """Set up Envisalink Field Programmer from a config entry."""
    host: str = entry.data[CONF_HOST]
    coordinator = VistaConsoleCoordinator(
        hass,
        entry,
        host=host,
        port=entry.data[CONF_PORT],
        password=entry.data[CONF_PASSWORD],
        num_partitions=entry.data[CONF_NUM_PARTITIONS],
        num_zones=entry.data[CONF_NUM_ZONES],
        keepalive_interval=entry.options.get(CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL),
        installer_code=entry.options.get(CONF_INSTALLER_CODE) or None,
        panel_model=entry.data.get(CONF_PANEL_MODEL, DEFAULT_PANEL_MODEL),
    )

    # A rejected password starts the reauth flow. Every other client failure,
    # including a refused command or a malformed frame during the first zone
    # timer dump, is a retry: the Envisalink admits one TPI client at a time
    # and a busy port looks exactly like an unreachable one.
    try:
        await coordinator.async_setup()
    except TPIAuthError as err:
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="invalid_auth",
            translation_placeholders={"host": host},
        ) from err
    except (TPIError, OSError) as err:
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="cannot_connect",
            translation_placeholders={"host": host, "error": str(err)},
        ) from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await async_register_frontend(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VistaConsoleConfigEntry) -> bool:
    """Unload a config entry. The actions stay registered; see async_setup."""
    unload_ok: bool = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: VistaConsoleConfigEntry) -> None:
    """Take this entry's repair issue with it when the entry is deleted."""
    ir.async_delete_issue(hass, DOMAIN, f"{ISSUE_TPI_SESSION_BUSY}_{entry.entry_id}")


async def _async_update_listener(hass: HomeAssistant, entry: VistaConsoleConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
