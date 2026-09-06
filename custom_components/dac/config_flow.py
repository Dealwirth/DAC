"""Config and options flow for DAC – Dynamic Alarm Clock."""
from __future__ import annotations

from datetime import time
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)
import voluptuous as vol

from .const import (
    CONF_ALARM_LIGHTS,
    CONF_ALARM_VOLUME,
    CONF_DEFAULT_ALARM_TIME,
    CONF_MEDIA_PLAYERS,
    CONF_NOTIFIER,
    CONF_OFFSET,
    CONF_REMINDER_TEXT,
    CONF_REMINDER_TIME,
    CONF_VACATION_CALENDARS,
    DEFAULT_ALARM_TIME,
    DEFAULT_ALARM_VOLUME,
    DEFAULT_NAME,
    DEFAULT_OFFSET_MINUTES,
    DEFAULT_REMINDER_TEXT,
    DEFAULT_REMINDER_TIME,
    DOMAIN,
)


def _notify_services(hass) -> list[str]:
    """Collect all available notify.* services for the selector."""
    services: list[str] = []
    for domain, services_map in hass.services.async_services().items():
        if domain != "notify":
            continue
        for service in services_map:
            if not service.startswith("_"):
                services.append(f"notify.{service}")
    return sorted(services) or ["notify.notify"]


def _time_to_str(value: Any, fallback: str) -> str:
    """Normalize a selector time value into a 'HH:MM' string."""
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, str) and value:
        return value
    return fallback


def _build_schema(hass, defaults: dict[str, Any]) -> vol.Schema:
    """Build the shared config/options schema."""
    return vol.Schema(
        {
            vol.Required(
                CONF_DEFAULT_ALARM_TIME,
                default=defaults.get(CONF_DEFAULT_ALARM_TIME, DEFAULT_ALARM_TIME),
            ): TimeSelector(),
            vol.Required(
                CONF_OFFSET,
                default=defaults.get(CONF_OFFSET, DEFAULT_OFFSET_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=600, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX)
            ),
            vol.Required(
                CONF_REMINDER_TIME,
                default=defaults.get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME),
            ): TimeSelector(),
            vol.Required(
                CONF_REMINDER_TEXT,
                default=defaults.get(CONF_REMINDER_TEXT, DEFAULT_REMINDER_TEXT),
            ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
            vol.Required(
                CONF_NOTIFIER,
                default=defaults.get(CONF_NOTIFIER, "notify.notify"),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=_notify_services(hass),
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_ALARM_LIGHTS,
                description={"suggested_value": defaults.get(CONF_ALARM_LIGHTS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="light", multiple=True)),
            vol.Optional(
                CONF_MEDIA_PLAYERS,
                description={"suggested_value": defaults.get(CONF_MEDIA_PLAYERS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
            vol.Optional(
                CONF_VACATION_CALENDARS,
                description={"suggested_value": defaults.get(CONF_VACATION_CALENDARS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="calendar", multiple=True)),
            vol.Required(
                CONF_ALARM_VOLUME,
                default=defaults.get(CONF_ALARM_VOLUME, DEFAULT_ALARM_VOLUME),
            ): NumberSelector(NumberSelectorConfig(min=0, max=1, step=0.05, mode=NumberSelectorMode.SLIDER)),
        }
    )


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Coerce selector output into JSON-serializable option values."""
    data = dict(user_input)
    data[CONF_DEFAULT_ALARM_TIME] = _time_to_str(
        data.get(CONF_DEFAULT_ALARM_TIME), DEFAULT_ALARM_TIME
    )
    data[CONF_REMINDER_TIME] = _time_to_str(
        data.get(CONF_REMINDER_TIME), DEFAULT_REMINDER_TIME
    )
    data[CONF_OFFSET] = int(data.get(CONF_OFFSET, DEFAULT_OFFSET_MINUTES))
    data[CONF_ALARM_VOLUME] = float(data.get(CONF_ALARM_VOLUME, DEFAULT_ALARM_VOLUME))
    for key in (CONF_ALARM_LIGHTS, CONF_MEDIA_PLAYERS, CONF_VACATION_CALENDARS):
        data.setdefault(key, [])
    return data


class DacConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial DAC setup."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show the setup form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _normalize(user_input)
            except (TypeError, ValueError):
                errors["base"] = "invalid_input"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=DEFAULT_NAME, data=data)
        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(self.hass, {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return DacOptionsFlow(config_entry)


class DacOptionsFlow(config_entries.OptionsFlow):
    """Handle DAC options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the entry for later use."""
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show the options form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                data = _normalize(user_input)
            except (TypeError, ValueError):
                errors["base"] = "invalid_input"
            else:
                return self.async_create_entry(title=DEFAULT_NAME, data=data)
        defaults: dict[str, Any] = {**self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(self.hass, defaults),
            errors=errors,
        )
