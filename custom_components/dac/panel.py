"""Static file registration for the DAC custom panel."""
from __future__ import annotations

import os

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import DOMAIN

PANEL_DIR = os.path.join(os.path.dirname(__file__), "www")
PANEL_JS = os.path.join(PANEL_DIR, "dac-panel.js")

PANEL_URL = "/dac/static/dac-panel.js"
PANEL_NAME = "dac-panel"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve the dashboard JS and register the sidebar panel."""
    await hass.http.async_register_static_paths(
        [StaticPathConfig(PANEL_URL, PANEL_JS, cache_headers=False)]
    )
    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="DAC Wecker",
        sidebar_icon="mdi:alarm",
        frontend_url_path="dac",
        require_admin=False,
        config={
            "_panel_custom": {
                "name": "dac-panel",
                "embed_iframe": False,
                "trust_external": False,
                "js_url": f"{PANEL_URL}?v=1",
            }
        },
    )
