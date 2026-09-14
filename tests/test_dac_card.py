"""Tests for the Lovelace card/dashboard auto-registration (dac_card.py)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dac.const import DOMAIN
from custom_components.dac.dac_card import DASHBOARD_URL_PATH, RESOURCE_URL


@pytest.fixture
async def lovelace(hass: HomeAssistant):
    """Set up lovelace in storage mode (like a normal HA instance)."""
    from homeassistant.components import lovelace

    existing = hass.data.get(lovelace.LOVELACE_DATA)
    if existing is not None:
        return existing
    with patch(
        "homeassistant.components.onboarding.async_is_onboarded", return_value=True
    ):
        await lovelace.async_setup(hass, {"lovelace": {"mode": "storage"}})
        await hass.async_block_till_done()
    return hass.data[lovelace.LOVELACE_DATA]


async def test_card_resource_registered(hass: HomeAssistant, lovelace) -> None:
    """dac-card.js is registered as a module resource in storage mode."""
    from custom_components.dac.dac_card import async_setup_lovelace

    await async_setup_lovelace(hass)

    items = lovelace.resources.async_items() or []
    urls = [item.get("url") for item in items if isinstance(item, dict)]
    assert RESOURCE_URL in urls
    types = [item.get("type") for item in items if isinstance(item, dict)]
    assert "module" in types


async def test_card_resource_idempotent(hass: HomeAssistant, lovelace) -> None:
    """Running setup twice must not duplicate the resource."""
    from custom_components.dac.dac_card import async_setup_lovelace

    await async_setup_lovelace(hass)
    await async_setup_lovelace(hass)

    items = lovelace.resources.async_items() or []
    urls = [item.get("url") for item in items if isinstance(item, dict)]
    assert urls.count(RESOURCE_URL) == 1


async def test_dashboard_created_with_initial_view(hass: HomeAssistant, lovelace) -> None:
    """A dedicated DAC dashboard with the card is created on first start."""
    from custom_components.dac.dac_card import async_setup_lovelace

    await async_setup_lovelace(hass)
    await hass.async_block_till_done()

    storage_dash = lovelace.dashboards[DASHBOARD_URL_PATH]
    config = await storage_dash.async_load(False)
    assert config["views"][0]["type"] == "custom:dac-wecker"

    # Sidebar panel registered.
    from homeassistant.components.frontend import DATA_PANELS

    assert DASHBOARD_URL_PATH in hass.data[DATA_PANELS]


async def test_dashboard_keeps_user_edits(hass: HomeAssistant, lovelace) -> None:
    """Existing dashboard config (user edits) is never overwritten."""
    from custom_components.dac.dac_card import async_setup_lovelace

    await async_setup_lovelace(hass)
    await hass.async_block_till_done()

    storage_dash = lovelace.dashboards[DASHBOARD_URL_PATH]
    edited = {"views": [{"title": "Meine View", "cards": []}]}
    await storage_dash.async_save(edited)

    await async_setup_lovelace(hass)
    await hass.async_block_till_done()

    config = await storage_dash.async_load(False)
    assert config["views"][0]["title"] == "Meine View"


async def test_yaml_mode_does_not_crash(hass: HomeAssistant) -> None:
    """YAML-mode lovelace or missing lovelace must never break DAC setup."""
    from custom_components.dac.dac_card import async_setup_lovelace

    # No lovelace at all -> silent skip.
    await async_setup_lovelace(hass)

    # Fake YAML mode -> resource registration skipped with a log message.
    class FakeYaml:
        resource_mode = "yaml"
        resources = None
        dashboards = {}

    hass.data["lovelace"] = FakeYaml()
    await async_setup_lovelace(hass)


async def test_setup_entry_registers_card(hass: HomeAssistant, config_entry) -> None:
    """The integration setup path calls the lovelace registration."""
    from types import SimpleNamespace

    from custom_components.dac import async_setup

    # The test hass has no HTTP app – provide a minimal stub.
    hass.http = SimpleNamespace(
        register_view=lambda view: None,
        async_register_static_paths=AsyncMock(return_value=None),
    )

    with patch(
        "custom_components.dac.async_setup_lovelace", new_callable=AsyncMock
    ) as reg:
        await async_setup(hass, {})
        await hass.async_block_till_done()
    reg.assert_awaited()
