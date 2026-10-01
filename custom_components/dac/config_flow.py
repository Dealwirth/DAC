"""Config and options flow for DAC – Dynamic Alarm Clock.

The initial setup deliberately shows **no form**: every setting lives in the
DAC sidebar panel. The options flow stays available as the HA-native fallback
and uses the same schema as the panel.
"""
from __future__ import annotations

from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN
from .settings import build_settings_schema, coerce_options, default_options


class DacConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial DAC setup (no questions – settings live in the panel)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Create the entry straight away with factory defaults."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="DAC", data=default_options())

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Return the HA-native options flow (fallback to the panel)."""
        return DacOptionsFlow(config_entry)


class DacOptionsFlow(config_entries.OptionsFlow):
    """Handle DAC options through the standard HA form."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the entry for later use."""
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show the options form."""
        if user_input is not None:
            data = coerce_options(user_input, {**self._entry.data, **self._entry.options})
            return self.async_create_entry(title="DAC", data=data)
        defaults: dict[str, Any] = {**default_options(), **self._entry.data, **self._entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=build_settings_schema(self.hass, defaults),
        )
