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
    PANEL_SETTINGS_ELEMENT,
    PANEL_SETTINGS_URL_PATH,
    PANEL_URL_PATH,
)

PANEL_JS = Path(__file__).parents[1] / "custom_components/dac/www/dac-panel.js"


async def test_panel_registered_in_sidebar(hass: HomeAssistant) -> None:
    """Both DAC panels are added to the sidebar via panel_custom."""
    from custom_components.dac.frontend import async_setup_frontend

    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock(return_value=None))
    with patch(
        "custom_components.dac.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await async_setup_frontend(hass)
        await hass.async_block_till_done()

    assert register.await_count == 2
    by_path = {call.kwargs["frontend_url_path"]: call.kwargs for call in register.await_args_list}

    control = by_path[PANEL_URL_PATH]
    assert control["webcomponent_name"] == PANEL_ELEMENT
    assert control["module_url"] == PANEL_MODULE_PATH
    assert control["embed_iframe"] is False

    settings = by_path[PANEL_SETTINGS_URL_PATH]
    assert settings["webcomponent_name"] == PANEL_SETTINGS_ELEMENT
    assert settings["module_url"] == PANEL_MODULE_PATH
    assert settings["embed_iframe"] is False


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
        # Simulate the panels being present from a previous run.
        hass.data.setdefault(DATA_PANELS, {})[PANEL_URL_PATH] = object()
        await async_setup_frontend(hass)
        await hass.async_block_till_done()

    assert register.await_count == 4


def test_panel_js_is_valid() -> None:
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
    """Both registered elements must be defined in the JS module."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert re.search(rf'customElements\.define\(\s*"{re.escape(PANEL_ELEMENT)}"', js)
    assert re.search(rf'customElements\.define\(\s*"{re.escape(PANEL_SETTINGS_ELEMENT)}"', js)


def test_panel_js_has_core_ui() -> None:
    """The panel ships simple time inputs, the month calendar and the test mode."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert 'type="time"' in js      # native, simple time picker
    assert "data-work" in js        # quick work-time chips
    assert "cal-grid" in js         # real month calendar
    assert "add_vacation" in js
    assert "alexa_set" in js
    assert "test_start" in js       # test mode integrated into the control page


def test_settings_live_on_their_own_page() -> None:
    """Settings moved to /dac-settings – the control panel has no save button."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "dac-settings-panel" in js
    assert 'href="/dac-settings"' in js
    assert "save_settings" in js
    # The settings fieldset is rendered by the settings element, not the control panel.
    control = js.split("class DacPanel")[1].split("class DacSettingsPanel")[0]
    assert "save-settings" not in control


def test_panel_js_offers_searchable_entity_suggestions() -> None:
    """Entity fields get a search input with live suggestion chips."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "data-suggest" in js
    assert "data-suggestions" in js
    assert "data-pick" in js
    assert "matchesEntity" in js
    assert "FIELD_DOMAINS" in js


def test_panel_js_has_no_tts_or_announcements() -> None:
    """DAC only places real device alarms – no TTS, no announcements."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "wake_text" not in js
    assert "media_players" not in js
    assert '"tts"' not in js

