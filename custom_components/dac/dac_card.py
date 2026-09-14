"""Lovelace integration for DAC: registers the DAC card and a ready dashboard.

* The JS card (``custom:dac-wecker``) is registered as a Lovelace *resource*
  (storage mode) so it can be added to ANY dashboard via the card picker.
* A dedicated sidebar dashboard "DAC Wecker" (url path ``dac-wecker``) is
  created on first start with the card already placed – fully editable in the
  UI and stored in its own .storage/lovelace.dac-wecker file.

Everything is idempotent and safe to run on every HA start.
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lovelace.const import LOVELACE_DATA, MODE_STORAGE
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

RESOURCE_URL = "/dac/static/dac-card.js"
DASHBOARD_URL_PATH = "dac-wecker"
DASHBOARD_TITLE = "DAC Wecker"

INITIAL_VIEW: dict[str, Any] = {
    "title": DASHBOARD_TITLE,
    "path": "dac",
    "icon": "mdi:alarm",
    "type": "custom:dac-wecker",
    "max_columns": 3,
    "badges": [],
    "cards": [{"type": "custom:dac-wecker"}],
}


async def async_setup_lovelace(hass: HomeAssistant) -> None:
    """Register card resource + dedicated dashboard (idempotent)."""
    lovelace_data = hass.data.get(LOVELACE_DATA)
    if lovelace_data is None:
        _LOGGER.debug("Lovelace not loaded – DAC card registration skipped")
        return
    await _async_register_resource(hass, lovelace_data)
    _async_register_dashboard(hass, lovelace_data)


async def _async_register_resource(hass: HomeAssistant, lovelace_data: Any) -> None:
    """Register dac-card.js as a Lovelace resource (storage mode only)."""
    resources = getattr(lovelace_data, "resources", None)
    if resources is None or getattr(lovelace_data, "resource_mode", None) != MODE_STORAGE:
        _LOGGER.info(
            "DAC card not auto-registered: Lovelace resources run in YAML mode – "
            "add '%s' (type: module) to your lovelace resources manually",
            RESOURCE_URL,
        )
        return
    try:
        existing = {item.get("url") for item in resources.async_items() or [] if isinstance(item, dict)}
        if RESOURCE_URL in existing:
            return
        await resources.async_create_item({"res_type": "module", "url": RESOURCE_URL})
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
