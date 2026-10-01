"""Tests for the DAC frontend panel registration (frontend.py)."""
from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant

from custom_components.dac.const import (
    PANEL_ELEMENT,
    PANEL_MODULE_PATH,
    PANEL_URL_PATH,
)

PANEL_JS = Path(__file__).parents[1] / "custom_components/dac/www/dac-panel.js"


async def test_panel_registered_in_sidebar(hass: HomeAssistant) -> None:
    """The DAC panel is added to the sidebar via panel_custom."""
    from custom_components.dac.frontend import async_setup_frontend

    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock(return_value=None))
    with patch(
        "custom_components.dac.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await async_setup_frontend(hass)
        await hass.async_block_till_done()

    register.assert_awaited()
    kwargs = register.await_args.kwargs
    assert kwargs["frontend_url_path"] == PANEL_URL_PATH
    assert kwargs["webcomponent_name"] == PANEL_ELEMENT
    assert kwargs["module_url"] == PANEL_MODULE_PATH
    assert kwargs["embed_iframe"] is False


async def test_static_module_served(hass: HomeAssistant) -> None:
    """The panel module is served from /dac/static/dac-panel.js."""
    from custom_components.dac.frontend import async_setup_frontend

    register = AsyncMock(return_value=None)
    hass.http = SimpleNamespace(async_register_static_paths=register)
    with patch(
        "custom_components.dac.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ):
        await async_setup_frontend(hass)
        await hass.async_block_till_done()

    register.assert_awaited()
    configs = register.await_args.args[0]
    assert configs[0].url_path == PANEL_MODULE_PATH


async def test_panel_registration_idempotent(hass: HomeAssistant) -> None:
    """Re-running setup must not raise and must re-register cleanly."""
    from homeassistant.components.frontend import DATA_PANELS

    from custom_components.dac.frontend import async_setup_frontend

    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock(return_value=None))
    with patch(
        "custom_components.dac.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await async_setup_frontend(hass)
        await hass.async_block_till_done()
        # Simulate the panel being present from a previous run.
        hass.data.setdefault(DATA_PANELS, {})[PANEL_URL_PATH] = object()
        await async_setup_frontend(hass)
        await hass.async_block_till_done()

    assert register.await_count == 2


async def test_panel_js_is_valid() -> None:
    """The shipped panel JS must be syntactically parseable."""
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        import pytest

        pytest.skip("node is not available")
    result = subprocess.run(
        [node, "--check", str(PANEL_JS)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_panel_element_matches_js() -> None:
    """The registered element must be defined in the JS module."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert re.search(rf'customElements\.define\(\s*"{re.escape(PANEL_ELEMENT)}"', js)


def test_panel_js_has_core_ui() -> None:
    """The panel ships simple time inputs, the month calendar and settings fields."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert 'type="time"' in js      # native, simple time picker
    assert "data-work" in js        # quick work-time chips
    assert "cal-grid" in js         # real month calendar
    assert "save_settings" in js    # settings live in the panel
    assert "add_vacation" in js
    assert "alexa_set" in js
    assert "test_start" in js       # test mode


def test_panel_js_offers_entity_suggestions() -> None:
    """Entity fields get a datalist and clickable suggestion chips."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "datalist" in js
    assert "dl-alarm_lights" in js or "dl-${key}" in js
    assert "data-append" in js


def test_panel_js_uses_entity_group_mapping() -> None:
    """The panel maps each option to the entity group from the API payload."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "ENTITY_GROUPS" in js
    assert "alarm_lights" in js and "media_players" in js
    assert "input_boolean" in js

