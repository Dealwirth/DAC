"""Lovelace integration for DAC: registers the DAC card and a ready dashboard.

* The JS card is served from ``/dac/static/dac-card.js`` and registered as a
  Lovelace *resource* (storage mode) so it can be added to ANY dashboard via
  the card picker as ``custom:dac-wecker``.
* A dedicated sidebar dashboard "DAC Wecker" (url path ``dac-wecker``) is
  created on first start with the card already placed – fully editable in the
  UI and stored in its own .storage/lovelace.dac-wecker file.

Everything is idempotent and safe to run on every HA start.
"""
from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.const import (
    LOVELACE_DATA,
    MODE_STORAGE,
)
from homeassistant.core import HomeAssistant, callback

from .const import (
    CARD_URL,
    CARD_URL_PATH,
    DASHBOARD_TITLE,
    DASHBOARD_URL_PATH,
)

_LOGGER = logging.getLogger(__name__)

CARD_JS = os.path.join(os.path.dirname(__file__), "www", "dac-card.js")
CARD_TYPE = f"custom:{CARD_URL}"

INITIAL_VIEW: dict[str, Any] = {
    "title": DASHBOARD_TITLE,
    "path": "dac",
    "icon": "mdi:alarm",
    "max_columns": 1,
    "cards": [{"type": CARD_TYPE}],
}


async def async_setup_lovelace(hass: HomeAssistant) -> None:
    """Register the static card file, resource and dedicated dashboard."""
    await _async_register_static(hass)
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Lovelace not loaded – DAC card registration skipped")
        return
    await _async_register_resource(hass, lovelace_data)
    _async_register_dashboard(hass, lovelace_data)


async def _async_register_static(hass: HomeAssistant) -> None:
    """Serve dac-card.js as a static file (idempotent)."""
    http = getattr(hass, "http", None)
    if http is None:
        _LOGGER.debug("HTTP component not available – DAC card file not served")
        return
    try:
        await http.async_register_static_paths(
            [StaticPathConfig(CARD_URL_PATH, CARD_JS, cache_headers=False)]
        )
    except RuntimeError:
        # Already registered (e.g. after a reload) – harmless.
        _LOGGER.debug("DAC card static path already registered")
    except Exception as err:  # noqa: BLE001 – never break startup over the card
        _LOGGER.warning("DAC could not serve the Lovelace card file: %s", err)


async def _async_register_resource(hass: HomeAssistant, lovelace_data: Any) -> None:
    """Register dac-card.js as a Lovelace resource (storage mode only)."""
    resources = getattr(lovelace_data, "resources", None)
    if resources is None or getattr(lovelace_data, "resource_mode", None) != MODE_STORAGE:
        _LOGGER.info(
            "DAC card not auto-registered: Lovelace resources run in YAML mode – "
            "add '%s' (type: module) to your lovelace resources manually",
            CARD_URL_PATH,
        )
        return
    try:
        existing = {item.get("url") for item in resources.async_items() or [] if isinstance(item, dict)}
        if CARD_URL_PATH in existing:
            return
        await resources.async_create_item({"res_type": "module", "url": CARD_URL_PATH})
        _LOGGER.info("DAC dashboard card registered as Lovelace resource")
    except Exception as err:  # noqa: BLE001 – never break startup over the card
        _LOGGER.warning("DAC could not register the Lovelace resource: %s", err)


@callback
def _async_register_dashboard(hass: HomeAssistant, lovelace_data: Any) -> None:
    """Create the DAC dashboard (own storage file) and its sidebar panel."""
    from homeassistant.components import frontend as fe
    from homeassistant.components.lovelace import dashboard as ll_dashboard

    dashboards = lovelace_data.dashboards
    storage_dash = dashboards.get(DASHBOARD_URL_PATH)
    if storage_dash is None:
        # The registry entry must contain "id" – LovelaceStorage derives its
        # .storage/lovelace.<id> file name from it.
        config = {
            "id": DASHBOARD_URL_PATH,
            "title": DASHBOARD_TITLE,
            "icon": "mdi:alarm",
            "url_path": DASHBOARD_URL_PATH,
            "mode": MODE_STORAGE,
            "require_admin": False,
            "show_in_sidebar": True,
        }
        storage_dash = ll_dashboard.LovelaceStorage(hass, config)
        dashboards[DASHBOARD_URL_PATH] = storage_dash

    async def _init_config() -> None:
        try:
            existing = await storage_dash.async_load(False)
        except Exception:  # noqa: BLE001
            existing = {}
        if not existing:
            try:
                await storage_dash.async_save({"views": [dict(INITIAL_VIEW)]})
                _LOGGER.info("DAC dashboard created at /%s", DASHBOARD_URL_PATH)
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("DAC dashboard could not be created: %s", err)

    hass.async_create_task(_init_config())

    panels = hass.data.get(fe.DATA_PANELS, {})
    update = DASHBOARD_URL_PATH in panels
    try:
        fe.async_register_built_in_panel(
            hass,
            "lovelace",
            sidebar_title=DASHBOARD_TITLE,
            sidebar_icon="mdi:alarm",
            frontend_url_path=DASHBOARD_URL_PATH,
            require_admin=False,
            config={"mode": MODE_STORAGE},
            update=update,
        )
    except ValueError:
        _LOGGER.debug("DAC dashboard panel already registered")
    except Exception as err:  # noqa: BLE001 – never break startup over the dashboard
        _LOGGER.warning("DAC dashboard panel registration failed: %s", err)
