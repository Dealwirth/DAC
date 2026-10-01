"""Tests for the DAC HTTP API used by the sidebar panel."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dac.const import (
    CONF_DEFAULT_ALARM_TIME,
    CONF_OFFSET,
    CONF_VACATION_KEYWORDS,
    DOMAIN,
)
from custom_components.dac.http_api import (
    DacApiView,
    _lookup_entity,
    _range_days,
)


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
    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    return config_entry


async def test_get_returns_full_payload(hass: HomeAssistant, loaded_entry) -> None:
    """GET /api/dac exposes state, settings, alexa and the calendar."""
    view = DacApiView()
    payload = _payload(await view.get(FakeRequest(hass)))

    assert len(payload["entries"]) == 1
    entry = payload["entries"][0]
    assert entry["entry_id"] == loaded_entry.entry_id
    assert set(entry) >= {"state", "mode", "alexa", "settings", "calendar", "alarm_target"}
    assert entry["alexa"]["enabled"] is False
    # Settings are complete – the panel renders every field from this payload.
    assert CONF_DEFAULT_ALARM_TIME in entry["settings"]
    assert CONF_OFFSET in entry["settings"]
    assert CONF_VACATION_KEYWORDS in entry["settings"]
    assert "own" in entry["calendar"] and "external" in entry["calendar"]


async def test_post_set_work_time(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    response = await view.post(
        FakeRequest(hass, {"action": "set_work_time", "time": "15:00"})
    )
    assert _payload(response) == {"ok": True}
    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    assert coordinator._work_time.strftime("%H:%M") == "15:00"


async def test_post_clear_work_time(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    await view.post(FakeRequest(hass, {"action": "set_work_time", "time": "15:00"}))
    assert _payload(await view.post(FakeRequest(hass, {"action": "clear_work_time"}))) == {"ok": True}
    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    assert coordinator._work_time is None


async def test_post_rejects_unknown_action(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    response = await view.post(FakeRequest(hass, {"action": "nope"}))
    assert response.status == 400


async def test_post_without_json_is_bad_request(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    assert (await view.post(FakeRequest(hass, None))).status == 400


async def test_post_missing_time_is_bad_request(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    assert (await view.post(FakeRequest(hass, {"action": "set_work_time"}))).status == 400


async def test_post_stop_and_mode(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    assert _payload(await view.post(FakeRequest(hass, {"action": "stop"}))) == {"ok": True}
    assert _payload(
        await view.post(FakeRequest(hass, {"action": "mode", "mode": "dismissed"}))
    ) == {"ok": True}
    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    assert coordinator.current_mode == "dismissed"


async def test_post_saves_settings(hass: HomeAssistant, loaded_entry) -> None:
    """The panel can change every setting through save_settings."""
    view = DacApiView()
    response = await view.post(
        FakeRequest(
            hass,
            {
                "action": "save_settings",
                "settings": {
                    "offset_minutes": 30,
                    "default_alarm_time": "07:15",
                    "alarm_lights": "light.a, light.b",
                    "alexa_enabled": True,
                    "vacation_keywords": "urlaub, brückentag",
                    "junk_key": "ignored",
                },
            },
        )
    )
    assert _payload(response) == {"ok": True}

    options = loaded_entry.options
    assert options["offset_minutes"] == 30
    assert options["default_alarm_time"] == "07:15:00"
    assert options["alarm_lights"] == ["light.a", "light.b"]
    assert options["alexa_enabled"] is True
    assert options[CONF_VACATION_KEYWORDS] == "urlaub, brückentag"
    assert "junk_key" not in options

    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    assert coordinator.options["offset_minutes"] == 30


async def test_post_save_settings_rejects_non_object(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    response = await view.post(FakeRequest(hass, {"action": "save_settings", "settings": 5}))
    assert response.status == 400


async def test_lookup_entity_finds_calendar(hass: HomeAssistant, loaded_entry) -> None:
    entity = _lookup_entity(hass, "calendar.dac_urlaubskalender")
    assert entity is not None
    assert hasattr(entity, "async_delete_event")
    assert _lookup_entity(hass, "calendar.does_not_exist") is None


async def test_add_remove_and_clear_vacation(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    add = await view.post(
        FakeRequest(
            hass,
            {
                "action": "add_vacation",
                "start": "2026-09-20",
                "end": "2026-09-21",
                "summary": "Urlaub",
            },
        )
    )
    assert _payload(add) == {"ok": True}

    calendar = _lookup_entity(hass, "calendar.dac_urlaubskalender")
    assert calendar is not None
    assert len(calendar._events) == 2  # one all-day event per day
    uid = calendar._events[0]["uid"]

    remove = await view.post(FakeRequest(hass, {"action": "remove_vacation", "uid": uid}))
    assert _payload(remove) == {"ok": True}
    assert len(calendar._events) == 1

    clear = await view.post(FakeRequest(hass, {"action": "clear_vacations"}))
    assert _payload(clear) == {"ok": True}
    assert calendar._events == []


async def test_add_vacation_invalid_range(hass: HomeAssistant, loaded_entry) -> None:
    view = DacApiView()
    response = await view.post(
        FakeRequest(hass, {"action": "add_vacation", "start": "nope", "end": "nope"})
    )
    assert response.status == 400


@pytest.mark.usefixtures("loaded_entry")
@freeze_time("2026-09-15 08:00:00")
async def test_calendar_payload_marks_own_days(hass: HomeAssistant, loaded_entry) -> None:
    """Days stored on the DAC calendar show up as 'own' for the month grid."""
    view = DacApiView()
    await view.post(
        FakeRequest(hass, {"action": "add_vacation", "start": "2026-09-20", "end": "2026-09-20"})
    )
    entry = _payload(await view.get(FakeRequest(hass)))["entries"][0]
    days = {day["date"] for day in entry["calendar"]["own"]}
    assert "2026-09-20" in days
    assert entry["calendar"]["start"] <= "2026-09-20" <= entry["calendar"]["end"]


def test_range_days_swaps_and_expands() -> None:
    days = _range_days("2026-09-21", "2026-09-19")
    assert [d.isoformat() for d in days] == ["2026-09-19", "2026-09-20", "2026-09-21"]
    assert _range_days(None, None) == []
