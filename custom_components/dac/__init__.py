"""The DAC – Dynamic Alarm Clock integration."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import voluptuous as vol

from .const import (
    ATTR_DAY,
    ATTR_TIME,
    CONF_ALARM_LIGHTS,
    CONF_DEFAULT_ALARM_TIME,
    CONF_MEDIA_PLAYERS,
    CONF_NOTIFIER,
    CONF_OFFSET,
    CONF_REMINDER_TEXT,
    CONF_REMINDER_TIME,
    CONF_VACATION_CALENDARS,
    DOMAIN,
    PLATFORMS,
    SERVICE_DISMISS_FOR_TODAY,
    SERVICE_SET_WORK_TIME,
    SERVICE_STOP_ALARM,
)
from .coordinator import DacCoordinator
from .http_api import DacApiView
from .logic import parse_time_str
from .panel import async_register_panel
from .store import DacStore

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SET_WORK_TIME_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_TIME): vol.Any(str, cv.time),
        vol.Optional(ATTR_DAY): str,
        vol.Optional("clear"): bool,
    }
)
DISMISS_SCHEMA = vol.Schema({vol.Optional(ATTR_DAY): str})
STOP_SCHEMA = vol.Schema({})

_SERVICE_MAP = {
    SERVICE_SET_WORK_TIME: (SET_WORK_TIME_SCHEMA, SupportsResponse.NONE),
    SERVICE_STOP_ALARM: (STOP_SCHEMA, SupportsResponse.NONE),
    SERVICE_DISMISS_FOR_TODAY: (DISMISS_SCHEMA, SupportsResponse.NONE),
}


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the HTTP API and the custom dashboard panel (once)."""
    hass.http.register_view(DacApiView())
    await async_register_panel(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up DAC from a config entry."""
    store = DacStore(hass, entry.entry_id)
    coordinator = DacCoordinator(hass, entry, store=store)
    await coordinator.async_restore_state(await store.async_load())

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    for service, (schema, supports) in _SERVICE_MAP.items():
        hass.services.async_register(
            DOMAIN, service, _make_handler(hass, service), schema=schema, supports_response=supports
        )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _make_handler(hass: HomeAssistant, service: str) -> Any:
    """Build a service handler resolving the target coordinator."""

    async def handler(call: ServiceCall) -> None:
        coordinators: dict[str, DacCoordinator] = hass.data[DOMAIN]
        if call.data.get("config_entry_id"):
            entry_id = call.data["config_entry_id"]
            if entry_id not in coordinators:
                raise HomeAssistantError(f"Unknown config entry: {entry_id}")
            coordinator = coordinators[entry_id]
        elif len(coordinators) == 1:
            coordinator = next(iter(coordinators.values()))
        elif call.data.get("device_id") or call.data.get("entity_id"):
            raise HomeAssistantError(
                "Multiple DAC entries found – pass config_entry_id explicitly"
            )
        else:
            coordinator = next(iter(coordinators.values()))

        if service == SERVICE_SET_WORK_TIME:
            await coordinator.async_set_work_time(call)
        elif service == SERVICE_STOP_ALARM:
            await coordinator.async_stop_alarm(call)
        elif service == SERVICE_DISMISS_FOR_TODAY:
            await coordinator.async_dismiss_for_today(call)

    return handler


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options updates."""
    coordinator: DacCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_set_options(dict(entry.options))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: DacCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_shutdown()
        for service in _SERVICE_MAP:
            hass.services.async_remove(DOMAIN, service)
    return unload_ok
