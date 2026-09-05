"""Shared base entities for Envisalink Field Programmer platforms."""

from __future__ import annotations

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_HOST, CONF_MAC, DOMAIN
from .coordinator import VistaConsoleCoordinator
from .field_programming import ProgrammingForm


class VistaConsoleEntity(CoordinatorEntity[VistaConsoleCoordinator]):
    """Base entity wiring shared device info back to the panel/EVL."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: VistaConsoleCoordinator, unique_id_suffix: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{unique_id_suffix}"

    @property
    def device_info(self) -> DeviceInfo:
        entry = self.coordinator.entry
        info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Honeywell / EyezOn",
            model="VISTA panel via Envisalink EVL-3/EVL-4",
            # The Envisalink's own web page, where its password, network
            # settings and firmware live.
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        )
        # Only a DHCP discovery can learn the MAC; TPI never reports it.
        if mac := entry.data.get(CONF_MAC):
            info["connections"] = {(CONNECTION_NETWORK_MAC, mac)}
        return info

    @property
    def available(self) -> bool:
        return bool(super().available and self.coordinator.data.system.connected)


class ProgrammingEntity(VistaConsoleEntity):
    """Base for the entities that make up the device page's programming form.

    Every one of them is a configuration entity: setting it writes to the
    entry's :class:`ProgrammingForm` and nothing else. Only a button press
    sends anything to the panel, and only with the confirm switch on.
    """

    _attr_entity_category = EntityCategory.CONFIG

    @property
    def form(self) -> ProgrammingForm:
        return self.coordinator.programming


def programming_entity_display_name(hass: HomeAssistant, entry_id: str, suffix: str) -> str:
    """The name a programming entity shows the user, for refusal messages.

    Read from the entity registry at the moment of the refusal, so the message
    names the entity in the user's language and honours a rename instead of
    repeating the English default.
    """
    registry = er.async_get(hass)
    unique_id = f"{entry_id}_{suffix}"
    for entity in er.async_entries_for_config_entry(registry, entry_id):
        if entity.unique_id == unique_id:
            return entity.name or entity.original_name or entity.entity_id
    return suffix.removeprefix("program_").replace("_", " ")
