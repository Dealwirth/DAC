"""Tests for the DAC frontend dashboard registration (frontend.py)."""
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


async def test_dashboard_registered_in_sidebar(hass: HomeAssistant) -> None:
    """The DAC dashboard is added to the sidebar as one entry via panel_custom."""
    from custom_components.dac.frontend import async_setup_frontend

    hass.http = SimpleNamespace(async_register_static_paths=AsyncMock(return_value=None))
    with patch(
        "custom_components.dac.frontend.panel_custom.async_register_panel",
        new=AsyncMock(),
    ) as register:
        await async_setup_frontend(hass)
        await hass.async_block_till_done()

    assert register.await_count == 1
    call = register.await_args_list[0].kwargs
    assert call["frontend_url_path"] == PANEL_URL_PATH
    assert call["webcomponent_name"] == PANEL_ELEMENT
    assert call["module_url"] == PANEL_MODULE_PATH
    assert call["embed_iframe"] is False


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
    """The registered element must be defined in the JS module."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert re.search(rf'customElements\.define\(\s*"{re.escape(PANEL_ELEMENT)}"', js)


def test_panel_js_has_core_ui() -> None:
    """The dashboard ships simple time inputs, the month calendar and test mode."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert 'type="time"' in js      # native, simple time picker
    assert "data-work" in js        # quick work-time chips
    assert "cal-grid" in js         # real month calendar
    assert "add_vacation" in js
    assert "alexa_set" in js
    assert "test_start" in js       # test mode integrated into the home page


def test_dashboard_has_pages() -> None:
    """One dashboard hosts several pages (Home, Kalender, Einstellungen, Hilfe)."""
    js = PANEL_JS.read_text(encoding="utf-8")
    for page in ("home", "calendar", "settings", "help"):
        assert f'"{page}"' in js
    assert "data-page" in js        # in-page navigation
    assert "_settingsPage" in js    # settings is a page, not a second panel
    assert "save_settings" in js
    # There is only one custom element now – the settings panel is gone.
    assert "dac-settings-panel" not in js
    assert not re.search(r'customElements\.define\(\s*"dac-settings', js)


def test_panel_js_offers_live_entity_search() -> None:
    """Entity fields are real search inputs with live, ranked suggestions."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "data-search" in js
    assert "data-suggestions" in js
    assert "data-pick" in js
    assert "data-unpick" in js
    assert "searchEntities" in js
    assert "FIELD_DOMAINS" in js
    assert "auch gefunden" in js    # cross-domain hits are shown too


def test_panel_js_has_no_tts_or_announcements() -> None:
    """DAC only places real device alarms – no TTS, no announcements."""
    js = PANEL_JS.read_text(encoding="utf-8")
    assert "wake_text" not in js
    assert "media_players" not in js
    assert '"tts"' not in js


def test_entity_search_ranks_domain_hits_first() -> None:
    """The shipped search function: domain hits first, cross-domain after.

    This runs the real ``searchEntities`` from the panel module so the
    behaviour the user sees in the picker is what is asserted here.
    """
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        import pytest

        pytest.skip("node is not available")

    js = PANEL_JS.read_text(encoding="utf-8")
    start = js.index("function searchEntities")
    end = js.index("/** Basisklasse")
    fn = "const MAX_SUGGESTIONS = 10;\n" + js[start:end]
    harness = fn + """
const items = [
  { id: "light.echo_lampe", name: "Echo Lampe", domain: "light", area: "", alexa: true },
  { id: "media_player.echo_kuche", name: "Echo Küche", domain: "media_player", area: "Küche", alexa: true },
  { id: "media_player.sonos", name: "Sonos", domain: "media_player", area: "", alexa: false },
  { id: "sensor.echo_temperatur", name: "Echo Temperatur", domain: "sensor", area: "", alexa: true },
];
const byArea = searchEntities(items, "küche", ["media_player"]);
const byName = searchEntities(items, "echo", ["media_player"]);
const empty = searchEntities(items, "", ["media_player"]);
console.log(JSON.stringify({
  areaFirst: byArea.primary[0] && byArea.primary[0].id,
  nameFirst: byName.primary[0] && byName.primary[0].id,
  nameExtra: byName.extra.map((i) => i.id),
  emptyCount: empty.primary.length,
  emptyHasSensor: empty.primary.some((i) => i.domain === "sensor"),
}));
"""
    result = subprocess.run(
        [node, "-e", harness], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    # A search by room finds the Echo even without knowing its entity id.
    assert data["areaFirst"] == "media_player.echo_kuche"
    # Domain matches come first, other domains show up under "auch gefunden".
    assert data["nameFirst"] == "media_player.echo_kuche"
    assert "sensor.echo_temperatur" in data["nameExtra"]
    # Without a query only the field's domains are offered.
    assert data["emptyCount"] == 2
    assert data["emptyHasSensor"] is False

