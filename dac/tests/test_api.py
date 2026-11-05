"""Tests for the DAC app's HTTP API (the Ingress UI backend)."""
from __future__ import annotations

import httpx

from app.config import settings
from app.main import app


def _client() -> httpx.AsyncClient:
    """An ASGI client (the lifespan/scheduler is intentionally not started)."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://dac")


async def test_health() -> None:
    async with _client() as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


async def test_index_serves_ui() -> None:
    async with _client() as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "DAC" in response.text
    assert "--alexa:#00caff" in response.text  # Alexa look


async def test_state_contains_state_settings_alexa(fake_ha) -> None:
    settings.update({"alexa_media_player": "media_player.echo"})
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    fake_ha.set_state("input_boolean.wecker_aktiv", "on")
    async with _client() as client:
        payload = (await client.get("/api/state")).json()
    assert set(payload) == {"version", "state", "settings", "alexa", "ha"}
    assert payload["alexa"]["player"] == "media_player.echo"
    assert payload["alexa"]["stored_alarm"] == "05:43"
    assert payload["alexa"]["gate_on"] is True


async def test_settings_are_masked(fake_ha) -> None:
    settings.update({"mqtt_password": "geheim"})
    async with _client() as client:
        payload = (await client.get("/api/state")).json()
    assert payload["settings"]["mqtt_password"] == "********"


async def test_post_settings_applies_and_persists(fake_ha) -> None:
    async with _client() as client:
        response = await client.post(
            "/api/settings", json={"offset_minutes": 45, "alarm_lights": ["light.sz"]}
        )
    assert response.status_code == 200
    assert settings.get("offset_minutes") == 45
    assert settings.get_list("alarm_lights") == ["light.sz"]


async def test_post_settings_rejects_unknown_key(fake_ha) -> None:
    async with _client() as client:
        response = await client.post("/api/settings", json={"ha_token": "hack"})
    assert response.status_code == 400


async def test_action_set_work_time(fake_ha) -> None:
    settings.update({"alexa_media_player": "media_player.echo"})
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "")
    async with _client() as client:
        response = await client.post(
            "/api/action", json={"action": "set_work_time", "time": "06:45"}
        )
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert fake_ha.calls_for("media_player", "play_media")


async def test_action_rejects_unknown(fake_ha) -> None:
    async with _client() as client:
        response = await client.post("/api/action", json={"action": "explode"})
    assert response.status_code == 400


async def test_action_set_work_time_without_time(fake_ha) -> None:
    async with _client() as client:
        response = await client.post("/api/action", json={"action": "set_work_time"})
    assert response.status_code == 400


async def test_action_mode_invalid(fake_ha) -> None:
    async with _client() as client:
        response = await client.post("/api/action", json={"action": "mode", "mode": "nonsense"})
    assert response.status_code == 400


async def test_entities_are_grouped(fake_ha) -> None:
    fake_ha.set_state("light.schlafzimmer", "off", {"friendly_name": "Schlafzimmer"})
    fake_ha.set_state("calendar.urlaub", "off", {"friendly_name": "Urlaub"})
    async with _client() as client:
        groups = (await client.get("/api/entities")).json()["groups"]
    assert groups["light"][0]["entity_id"] == "light.schlafzimmer"
    assert "calendar" in groups


async def test_simulate_work_time(fake_ha) -> None:
    settings.update({"offset_minutes": 60})
    async with _client() as client:
        payload = (await client.get("/api/simulate?work=06:45")).json()
    assert payload["alarm_time"] == "05:45"
    assert payload["offset_minutes"] == 60


async def test_simulate_rejects_bad_time(fake_ha) -> None:
    async with _client() as client:
        response = await client.get("/api/simulate?work=nope")
    assert response.status_code == 400


async def test_help_lists_sections(fake_ha) -> None:
    async with _client() as client:
        payload = (await client.get("/api/help")).json()
    assert len(payload["sections"]) >= 4


async def test_index_injects_ingress_base(fake_ha) -> None:
    """The UI must carry the Ingress base path so assets resolve."""
    async with _client() as client:
        response = await client.get("/", headers={"X-Ingress-Path": "/api/hassio_ingress/abc"})
    assert '<base href="/api/hassio_ingress/abc/" />' in response.text
    assert response.headers["X-Ingress-Path"] == "/api/hassio_ingress/abc"


async def test_index_without_ingress_uses_root_base(fake_ha) -> None:
    async with _client() as client:
        response = await client.get("/")
    assert '<base href="/" />' in response.text


async def test_unknown_path_falls_back_to_ui(fake_ha) -> None:
    async with _client() as client:
        response = await client.get("/wecker")
    assert response.status_code == 200
    assert "DAC" in response.text


async def test_static_file_is_served(fake_ha) -> None:
    async with _client() as client:
        response = await client.get("/static/index.html")
    assert response.status_code == 200
