"""Persistent storage for the DAC alarm state (survives restarts)."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN, STORAGE_VERSION


class DacStore:
    """Small wrapper around a Home Assistant Store instance."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the store keyed by config entry."""
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")

    async def async_load(self) -> dict:
        """Load the saved state or return an empty dict."""
        return await self._store.async_load() or {}

    async def async_save(self, data: dict) -> None:
        """Persist the given state payload."""
        await self._store.async_save(data)
