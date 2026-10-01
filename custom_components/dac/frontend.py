"""Frontend integration for DAC: serves the panel and adds it to the sidebar.

* ``dac-panel.js`` is served from ``/dac/static/dac-panel.js``.
* A custom sidebar panel "DAC" (url path ``/dac``) is registered via
  ``panel_custom`` – the whole configuration happens inside that page.

Everything is idempotent and safe to run on every HA start.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components import panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback

from .const import (
    PANEL_ELEMENT,
    PANEL_MODULE_PATH,
    PANEL_TITLE,
    PANEL_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

PANEL_JS = os.path.join(os.path.dirname(__file__), "www", "dac-panel.js")
PANEL_ICON = "mdi:alarm"


async def async_setup_frontend(hass: HomeAssistant) -> None:
    """Serve the panel module and register the sidebar panel."""
    await _async_register_static(hass)
    _async_register_panel(hass)


async def _async_register_static(hass: HomeAssistant) -> None:
    """Serve dac-panel.js as a static file (idempotent)."""
    http = getattr(hass, "http", None)
    if http is None:
        _LOGGER.debug("HTTP component not available – DAC panel file not served")
        return
    try:
        await http.async_register_static_paths(
            [StaticPathConfig(PANEL_MODULE_PATH, PANEL_JS, cache_headers=False)]
        )
    except RuntimeError:
        # Already registered (e.g. after a reload) – harmless.
        _LOGGER.debug("DAC panel static path already registered")
    except Exception as err:  # noqa: BLE001 – never break startup over the panel
        _LOGGER.warning("DAC could not serve the panel file: %s", err)


@callback
def _async_register_panel(hass: HomeAssistant) -> None:
    """Add the DAC panel to the sidebar (idempotent)."""
    hass.async_create_task(_async_register_panel_impl(hass))


async def _async_register_panel_impl(hass: HomeAssistant) -> None:
    """Register the panel, tolerating an already existing registration."""
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            module_url=PANEL_MODULE_PATH,
            embed_iframe=False,
            config=panel_config(),
            require_admin=False,
        )
        _LOGGER.info("DAC panel registered at /%s", PANEL_URL_PATH)
    except ValueError:
        _LOGGER.debug("DAC panel already registered")
    except Exception as err:  # noqa: BLE001 – never break startup over the panel
        _LOGGER.warning("DAC panel registration failed: %s", err)


def panel_config() -> dict[str, Any]:
    """Extra config handed to the panel element (kept minimal on purpose)."""
    return {"panel": True}
