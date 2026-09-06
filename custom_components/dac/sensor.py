"""Sensor platform for DAC – exposes the next alarm."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
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
    """Set up the DAC sensor from a config entry."""
    coordinator: DacCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([DacNextAlarmSensor(coordinator, entry)])


class _DacEntity(CoordinatorEntity[DacCoordinator]):
    """Base entity with a proper device entry and stable entity_id."""

    _attr_has_entity_name = False

    def __init__(self, coordinator: DacCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry_id)},
            name=DEVICE_NAME,
            manufacturer="Dealwirth",
            entry_type=DeviceEntryType.SERVICE,
        )


class DacNextAlarmSensor(_DacEntity, SensorEntity):
    """Sensor showing the next computed alarm time and status."""

    _attr_translation_key = "next_alarm"
    _attr_name = "DAC Next Alarm"
    _attr_unique_id = f"{DOMAIN}_next_alarm"
    _attr_icon = "mdi:alarm"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_should_poll = False

    @property
    def native_value(self) -> datetime | None:
        """The concrete next alarm firing time (with offset applied)."""
        target = self.coordinator.data.get("alarm_target")
        if not target:
            return None
        parsed = datetime.fromisoformat(str(target))
        return parsed

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Rich attributes for dashboard and automations."""
        data = self.coordinator.data
        attrs = dict(data)
        attrs["friendly_status"] = self._friendly_status(data)
        return attrs

    @staticmethod
    def _friendly_status(data: dict[str, Any]) -> str:
        """Human readable status (German)."""
        state = data.get("state")
        if data.get("vacation"):
            return "Urlaub / Feiertag – Wecker aus"
        mapping = {
            "idle": "Warte auf Eingabe",
            "scheduled": "Wecker gestellt",
            "ringing": "⏰ WECKT GERADE",
            "stopped": "Gestoppt",
            "dismissed": "Deaktiviert",
            "vacation": "Urlaub / Feiertag",
        }
        return mapping.get(state, state or "unbekannt")
