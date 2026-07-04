"""The Envisalink Field Programmer integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .client import TPIAuthError, TPIConnectionError
from .const import (
    CONF_HOST,
    CONF_INSTALLER_CODE,
    CONF_KEEPALIVE_INTERVAL,
    CONF_NUM_PARTITIONS,
    CONF_NUM_ZONES,
    CONF_PASSWORD,
    CONF_PORT,
    DEFAULT_KEEPALIVE_INTERVAL,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import VistaConsoleCoordinator
from .field_programming_services import async_register_field_programming_services
from .frontend import async_register_frontend
from .programming import async_register_services

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Envisalink Field Programmer from a config entry."""
    coordinator = VistaConsoleCoordinator(
        hass,
        entry,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        password=entry.data[CONF_PASSWORD],
        num_partitions=entry.data[CONF_NUM_PARTITIONS],
        num_zones=entry.data[CONF_NUM_ZONES],
        keepalive_interval=entry.options.get(
            CONF_KEEPALIVE_INTERVAL, DEFAULT_KEEPALIVE_INTERVAL
        ),
        installer_code=entry.options.get(CONF_INSTALLER_CODE) or None,
    )

    try:
        await coordinator.async_setup()
    except TPIAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except (TPIConnectionError, OSError) as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async_register_services(hass)
    async_register_field_programming_services(hass)
    await async_register_frontend(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: VistaConsoleCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
