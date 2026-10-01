"""Frontend integration for DAC: serves the dashboard and adds it to the sidebar.

* ``dac-panel.js`` is served from ``/dac/static/dac-panel.js``.
* One custom sidebar panel "DAC" (url path ``/dac``) hosts the whole
  dashboard – Home, Kalender, Einstellungen und Hilfe sind Seiten (Tabs)
  innerhalb dieser einen Seite.

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
    """Serve the panel module and register the DAC dashboard."""
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
    """Add the DAC dashboard to the sidebar (idempotent)."""
    hass.async_create_task(
        _async_register_panel_impl(
            hass,
            url_path=PANEL_URL_PATH,
            title=PANEL_TITLE,
            icon=PANEL_ICON,
        )
    )


async def _async_register_panel_impl(
    hass: HomeAssistant,
    *,
    url_path: str,
    title: str,
    icon: str,
) -> None:
    """Register the dashboard, tolerating an already existing registration."""
    try:
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=url_path,
            webcomponent_name=PANEL_ELEMENT,
            sidebar_title=title,
            sidebar_icon=icon,
            module_url=PANEL_MODULE_PATH,
            embed_iframe=False,
            config=panel_config(),
            require_admin=False,
        )
        _LOGGER.info("DAC dashboard registered at /%s", url_path)
    except ValueError:
        _LOGGER.debug("DAC panel /%s already registered", url_path)
    except Exception as err:  # noqa: BLE001 – never break startup over the panel
        _LOGGER.warning("DAC panel /%s registration failed: %s", url_path, err)


def panel_config() -> dict[str, Any]:
    """Extra config handed to the panel element (kept minimal on purpose)."""
    return {"panel": True}
