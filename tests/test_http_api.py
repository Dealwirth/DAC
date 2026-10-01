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
    CONF_TEST_MODE_MINUTES,
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


async def test_get_exposes_entity_suggestions(hass: HomeAssistant, loaded_entry) -> None:
    """GET /api/dac offers one flat, searchable list of entities for the pickers."""
    hass.states.async_set("light.bedroom", "off", {"friendly_name": "Schlafzimmer"})
    hass.states.async_set("media_player.echo", "idle", {"friendly_name": "Echo"})
    hass.states.async_set("input_boolean.wecker_aktiv", "off", {})
    hass.states.async_set("sensor.arbeit", "8", {"friendly_name": "Arbeit"})
    hass.states.async_set("sun.sun", "above_horizon", {})

    view = DacApiView()
    entry = _payload(await view.get(FakeRequest(hass)))["entries"][0]
    entities = entry["entities"]
    ids = [i["id"] for i in entities]
    assert "light.bedroom" in ids
    assert "media_player.echo" in ids
    assert "input_boolean.wecker_aktiv" in ids
    # Sensors and helpers are searchable too – like the classic YAML script.
    assert "sensor.arbeit" in ids
    # Noisy internal domains are skipped.
    assert "sun.sun" not in ids
    # Every item carries the domain so the panel can filter locally.
    by_id = {i["id"]: i for i in entities}
    assert by_id["light.bedroom"]["domain"] == "light"
    assert by_id["light.bedroom"]["name"] == "Schlafzimmer"


async def test_post_test_mode_start_and_cancel(hass: HomeAssistant, loaded_entry) -> None:
    """The panel can arm and cancel a test alarm through the API."""
    view = DacApiView()
    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]

    start = await view.post(FakeRequest(hass, {"action": "test_start", "minutes": 2}))
    assert _payload(start) == {"ok": True}
    assert coordinator.test_mode_active is True

    entry = _payload(await view.get(FakeRequest(hass)))["entries"][0]
    assert entry["test_mode"] is True
    assert entry["test_target"] is not None

    cancel = await view.post(FakeRequest(hass, {"action": "test_cancel"}))
    assert _payload(cancel) == {"ok": True}
    assert coordinator.test_mode_active is False


async def test_post_test_mode_uses_configured_minutes(
    hass: HomeAssistant, loaded_entry
) -> None:
    """Without a body value the configured test duration is used."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    view = DacApiView()
    coordinator = hass.data[DOMAIN][loaded_entry.entry_id]
    coordinator._options[CONF_TEST_MODE_MINUTES] = 4

    await view.post(FakeRequest(hass, {"action": "test_start"}))
    assert coordinator.test_mode_active is True
    delta = coordinator._test_target - dt_util.now()
    assert timedelta(minutes=4) - timedelta(seconds=2) <= delta <= timedelta(minutes=4)


async def test_post_exposes_loop_interval(hass: HomeAssistant, loaded_entry) -> None:
    """The wake loop interval is part of the panel payload."""
    view = DacApiView()
    entry = _payload(await view.get(FakeRequest(hass)))["entries"][0]
    assert entry["loop_interval_minutes"] == 5
    assert entry["alexa"]["stop_word"] == "Wecker aus"
    assert entry["alexa"]["routine_name"] == "DAC Stopp"
