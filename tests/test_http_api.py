"""Tests for the DAC HTTP API used by the dashboard card."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dac.const import DOMAIN
from custom_components.dac.http_api import DacApiView, _lookup_entity


class FakeRequest:
    """Minimal aiohttp request stand-in for the view methods."""

    def __init__(self, hass: HomeAssistant, body: dict | None = None) -> None:
        self.app = {"hass": hass}
        self._body = body

    async def json(self) -> dict:
        if self._body is None:
            raise ValueError("no json")
        return self._body


def _payload(response) -> dict:
    return json.loads(response.text)


@pytest.fixture
async def loaded_entry(hass: HomeAssistant, config_entry: MockConfigEntry, options: dict):
    with patch("custom_components.dac.async_setup_lovelace", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


async def test_get_returns_entry_payload(hass: HomeAssistant, loaded_entry) -> None:
    """GET /api/dac exposes the dashboard state for every entry."""
    view = DacApiView()
    response = await view.get(FakeRequest(hass))

    payload = _payload(response)
    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["entry_id"] == loaded_entry.entry_id
    assert set(entry) >= {"state", "mode", "alexa", "alarm_target", "vacation_events"}
    assert entry["alexa"]["enabled"] is False


async def test_post_set_work_time(hass: HomeAssistant, loaded_entry) -> None:
    """POST set_work_time updates the coordinator (dashboard path)."""
    view = DacApiView()
    response = await view.post(
        FakeRequest(hass, {"action": "set_work_time", "time": "15:00"})
    )
    assert _payload(response) == {"ok": True}

    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    assert coordinator._work_time is not None
    assert coordinator._work_time.strftime("%H:%M") == "15:00"


async def test_post_rejects_unknown_action(hass: HomeAssistant, loaded_entry) -> None:
    """Unknown actions return HTTP 400 instead of crashing."""
    view = DacApiView()
    response = await view.post(FakeRequest(hass, {"action": "nope"}))
    assert response.status == 400


async def test_post_without_json_is_bad_request(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    response = await view.post(FakeRequest(hass, None))
    assert response.status == 400


async def test_post_missing_time_is_bad_request(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    response = await view.post(FakeRequest(hass, {"action": "set_work_time"}))
    assert response.status == 400


async def test_post_stop_and_mode(hass: HomeAssistant, loaded_entry) -> None:
    """stop and mode actions run through the coordinator."""
    view = DacApiView()
    assert _payload(await view.post(FakeRequest(hass, {"action": "stop"}))) == {"ok": True}
    assert _payload(
        await view.post(FakeRequest(hass, {"action": "mode", "mode": "dismissed"}))
    ) == {"ok": True}

    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    assert coordinator.current_mode == "dismissed"


async def test_lookup_entity_finds_calendar(hass: HomeAssistant, loaded_entry) -> None:
    """_lookup_entity resolves the DAC vacation calendar entity object."""
    entity = _lookup_entity(hass, "calendar.dac_urlaubskalender")
    assert entity is not None
    assert hasattr(entity, "async_delete_event")
    assert _lookup_entity(hass, "calendar.does_not_exist") is None


async def test_add_and_remove_vacation(hass: HomeAssistant, loaded_entry) -> None:
    """Vacation events can be added and removed through the API."""
    view = DacApiView()
    add = await view.post(
        FakeRequest(
            hass,
            {
                "action": "add_vacation",
                "start": "2026-09-20T00:00:00",
                "end": "2026-09-21T23:59:59",
                "summary": "Urlaub",
            },
        )
    )
    assert _payload(add) == {"ok": True}

    calendar = _lookup_entity(hass, "calendar.dac_urlaubskalender")
    assert calendar is not None
    assert len(calendar._events) == 1
    uid = calendar._events[0]["uid"]

    remove = await view.post(FakeRequest(hass, {"action": "remove_vacation", "uid": uid}))
    assert _payload(remove) == {"ok": True}
    assert calendar._events == []
