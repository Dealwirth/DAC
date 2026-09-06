"""Time platform for DAC – manual work time input (Zifferblatt-Dialog)."""
from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEVICE_NAME, DOMAIN
from .coordinator import DacCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the DAC work time input."""
    coordinator: DacCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DacWorkTimeEntity(coordinator, entry)])


class DacWorkTimeEntity(CoordinatorEntity[DacCoordinator], TimeEntity):
    """Set the work start time directly (the alarm is computed from it)."""

    _attr_translation_key = "work_time"
    _attr_name = "DAC Arbeitsbeginn"
    _attr_unique_id = f"{DOMAIN}_work_time"
    _attr_icon = "mdi:clock-time-eight"
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
    def native_value(self) -> time | None:
        """The manually set work start time, if any."""
        raw = self.coordinator.data.get("work_time")
        if not raw:
            return None
        return time.fromisoformat(str(raw))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose which day the manual time targets."""
        return {"work_time_day": self.coordinator.data.get("work_time_day")}

    async def async_set_value(self, value: time) -> None:
        """User picked a work start time – behaves like the set_work_time service."""
        await self.coordinator._async_set_work_time_impl(
            _FakeCall({"time": value.strftime("%H:%M:%S")})
        )
        await self.coordinator.async_save_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class _FakeCall:
    """Minimal ServiceCall stand-in for internal coordinator calls."""

    def __init__(self, data: dict) -> None:
        self.data = data
