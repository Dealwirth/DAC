"""Select platform for DAC – alarm mode (standard / dismissed / vacation)."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_NAME, DOMAIN, MODE_DISMISSED, MODE_STANDARD, MODE_VACATION
from .coordinator import DacCoordinator

OPTIONS = [MODE_STANDARD, MODE_DISMISSED, MODE_VACATION]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the DAC mode select."""
    coordinator: DacCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DacModeSelect(coordinator, entry)])


class DacModeSelect(CoordinatorEntity[DacCoordinator], SelectEntity):
    """Select the alarm mode: standard, dismissed for today, or vacation override."""

    _attr_translation_key = "mode"
    _attr_name = "DAC Modus"
    _attr_unique_id = f"{DOMAIN}_mode"
    _attr_options = OPTIONS
    _attr_icon = "mdi:alarm-multiple"
    _attr_should_poll = False

    def __init__(self, coordinator: DacCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=DEVICE_NAME,
            manufacturer="Dealwirth",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def current_option(self) -> str | None:
        """Currently active mode."""
        return self.coordinator.current_mode

    async def async_select_option(self, option: str) -> None:
        """Apply the selected mode in the coordinator."""
        await self.coordinator.async_set_mode(option)
