"""HTTP API endpoints for the DAC sidebar panel (no external dependencies).

Everything the panel needs is exposed under ``/api/dac``:

* ``GET``  – full state: alarm, options, Alexa status, vacation calendar days
* ``POST`` – actions: work time, stop/dismiss, mode, settings, Alexa, vacation

Vacation days are stored as whole-day events on the DAC vacation calendar, so
they show up in the normal Home Assistant calendar too. Days already covered by
an external calendar (matching the configured keywords) are marked as external
and cannot be deleted from DAC.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform as ep
from homeassistant.util import dt as dt_util

from .const import ALEXA_ROUTINE_NAME, DOMAIN
from .coordinator import DacCoordinator
from .logic import event_marks_vacation
from .settings import EDITABLE_KEYS, coerce_options, default_options, vacation_keywords

_LOGGER = logging.getLogger(__name__)

_CALENDAR_LOOKAHEAD_DAYS = 120
_CALENDAR_PAST_DAYS = 7
MAX_RANGE_DAYS = 400


class DacApiView(HomeAssistantView):
    """REST-ish API under /api/dac used by the DAC panel."""

    url = "/api/dac"
    name = "api:dac"
    requires_auth = True

    async def get(self, request) -> None:
        """Return the full panel state."""
        hass = request.app["hass"]
        payload = {"entries": []}
        for coordinator in _coordinators(hass):
            payload["entries"].append(await _entry_payload(hass, coordinator))
        return self.json(payload)

    async def post(self, request) -> None:
        """Execute an action."""
        hass = request.app["hass"]
        try:
            body = await request.json()
        except ValueError:
            return self.json_message("invalid json", 400)
        action = body.get("action")
        coordinators = _coordinators(hass)
        if not coordinators:
            return self.json_message("no dac entry configured", 404)
        coordinator = _pick_coordinator(hass, body.get("entry_id")) or coordinators[0]

        try:
            if action == "set_work_time":
                await _set_work_time(coordinator, body)
            elif action == "clear_work_time":
                await coordinator._async_set_work_time_impl(_Call({"clear": True}))
                await coordinator.async_save_state()
            elif action == "stop":
                await coordinator.async_stop_alarm(_Call({}))
            elif action == "test_start":
                await coordinator.async_start_test_alarm(_Call({"minutes": body.get("minutes")}))
            elif action == "test_cancel":
                await coordinator.async_cancel_test_alarm(_Call({}))
            elif action == "dismiss":
                await coordinator._async_dismiss_for(dt_util.now().date())
            elif action == "mode":
                await coordinator.async_set_mode(body.get("mode", "standard"))
            elif action == "save_settings":
                await _save_settings(hass, coordinator, body)
            elif action == "alexa_set":
                await coordinator.alexa.async_set_alarm(_Call({"time": body.get("time")}))
            elif action == "alexa_clear":
                await coordinator.alexa.async_clear_own()
            elif action == "alexa_sync":
                await coordinator.alexa.async_sync()
            elif action == "add_vacation":
                await _add_vacation(hass, coordinator, body)
            elif action == "remove_vacation":
                await _remove_vacation(hass, body)
            elif action == "clear_vacations":
                await _clear_vacations(hass)
            else:
                return self.json_message(f"unknown action: {action}", 400)
        except (HomeAssistantError, ValueError) as err:
            return self.json_message(str(err), 400)
        return self.json({"ok": True})


# --------------------------------------------------------------------- actions
async def _set_work_time(coordinator: DacCoordinator, body: dict) -> None:
    time_value = body.get("time")
    if not time_value:
        raise HomeAssistantError("missing time")
    data: dict[str, Any] = {"time": time_value}
    if body.get("day"):
        data["day"] = body["day"]
    await coordinator._async_set_work_time_impl(_Call(data))
    await coordinator.async_save_state()
    await coordinator.alexa.async_sync()


async def _save_settings(hass: HomeAssistant, coordinator: DacCoordinator, body: dict) -> None:
    """Persist panel settings onto the config entry and apply them live."""
    incoming = body.get("settings") or {}
    if not isinstance(incoming, dict):
        raise HomeAssistantError("settings must be an object")
    base = {**default_options(), **coordinator.config_entry.data, **coordinator.config_entry.options}
    merged = coerce_options(
        {key: incoming[key] for key in incoming if key in EDITABLE_KEYS}, base
    )
    entry = coordinator.config_entry
    hass.config_entries.async_update_entry(entry, options=merged)
    coordinator.async_set_options(dict(entry.options))


async def _add_vacation(hass: HomeAssistant, coordinator: DacCoordinator, body: dict) -> None:
    """Create a vacation day (or range) on the DAC vacation calendar."""
    entity_id = _first_calendar(hass)
    if not entity_id:
        raise HomeAssistantError("Kein DAC-Urlaubskalender gefunden")
    days = _range_days(body.get("start"), body.get("end"))
    if not days:
        raise HomeAssistantError("Bitte einen gültigen Zeitraum wählen")
    summary = str(body.get("summary") or "Urlaub").strip() or "Urlaub"
    entity = _lookup_entity(hass, entity_id)
    if entity is None or not hasattr(entity, "async_create_event"):
        raise HomeAssistantError("Urlaubskalender nicht verfügbar")
    # One all-day event per day keeps the month grid exact and makes single
    # days editable/deletable.
    for day in days:
        await entity.async_create_event(
            dtstart=day,
            dtend=day + timedelta(days=1),
            summary=summary,
            description=body.get("description") or "",
        )


async def _remove_vacation(hass: HomeAssistant, body: dict) -> None:
    """Delete a vacation event by uid from the DAC vacation calendar."""
    entity_id = _first_calendar(hass)
    if not entity_id:
        raise HomeAssistantError("Kein DAC-Urlaubskalender gefunden")
    uid = body.get("uid")
    if not uid:
        raise HomeAssistantError("uid required")
    entity = _lookup_entity(hass, entity_id)
    if entity is None or not hasattr(entity, "async_delete_event"):
        raise HomeAssistantError("Urlaubskalender nicht verfügbar")
    await entity.async_delete_event(uid)


async def _clear_vacations(hass: HomeAssistant) -> None:
    """Remove every event from the DAC vacation calendar."""
    entity_id = _first_calendar(hass)
    entity = _lookup_entity(hass, entity_id) if entity_id else None
    if entity is None or not hasattr(entity, "async_delete_event"):
        raise HomeAssistantError("Urlaubskalender nicht verfügbar")
    for event in list(getattr(entity, "_events", [])):
        uid = event.get("uid")
        if uid:
            await entity.async_delete_event(uid)


def _range_days(start: Any, end: Any) -> list[date]:
    """Expand an ISO date range into single days (inclusive)."""
    first = _parse_date(start)
    last = _parse_date(end) or first
    if first is None or last is None:
        return []
    if last < first:
        first, last = last, first
    if (last - first).days > MAX_RANGE_DAYS:
        return []
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    text = str(value).strip()
    try:
        if "T" in text:
            return dt_util.parse_datetime(text).date()
        return date.fromisoformat(text[:10])
    except (ValueError, AttributeError):
        return None


# -------------------------------------------------------------------- helpers
def _coordinators(hass: HomeAssistant) -> list[DacCoordinator]:
    """All loaded DAC coordinators."""
    return list((hass.data.get(DOMAIN) or {}).values())


def _pick_coordinator(hass: HomeAssistant, entry_id: str | None) -> DacCoordinator | None:
    """Pick a specific coordinator by entry id (if given and valid)."""
    if not entry_id:
        return None
    return (hass.data.get(DOMAIN) or {}).get(entry_id)


def _first_calendar(hass: HomeAssistant) -> str | None:
    """Find the first DAC vacation calendar entity.

    Prefers the entity registry (stable across renames) and falls back to the
    entity-id prefix so the panel keeps working in odd setups.
    """
    from homeassistant.helpers import entity_registry as er

    registry = er.async_get(hass)
    for entry in registry.entities.values():
        if entry.platform == DOMAIN and entry.domain == "calendar":
            return entry.entity_id
    for state in hass.states.async_all("calendar"):
        if state.entity_id.startswith("calendar.dac"):
            return state.entity_id
    return None


def _lookup_entity(hass: HomeAssistant, entity_id: str):
    """Find a live entity object by its entity id.

    ``entity_platform.async_get_platforms`` is the supported way to reach a
    platform's entities; the ``domain_entities`` index is a fast first try.
    """
    domain = entity_id.split(".", 1)[0]
    domain_entities = hass.data.get(ep.DATA_DOMAIN_ENTITIES) or {}
    entity = (domain_entities.get(domain) or {}).get(entity_id)
    if entity is not None:
        return entity

    for platform in ep.async_get_platforms(hass, domain):
        entity = platform.entities.get(entity_id)
        if entity is not None:
            return entity
    return None


async def _entry_payload(hass: HomeAssistant, coordinator: DacCoordinator) -> dict:
    """Build the panel payload for one DAC entry."""
    data = coordinator.data
    options = {**default_options(), **coordinator.config_entry.data, **coordinator.options}
    calendar = await _calendar_payload(hass, coordinator)
    return {
        "entry_id": coordinator.entry_id,
        "state": data.get("state"),
        "mode": data.get("mode"),
        "vacation": data.get("vacation"),
        "work_time": data.get("work_time"),
        "work_time_day": data.get("work_time_day"),
        "alarm_time": data.get("alarm_time"),
        "alarm_day": data.get("alarm_day"),
        "alarm_target": data.get("alarm_target"),
        "offset_minutes": data.get("offset_minutes"),
        "default_alarm_time": data.get("default_alarm_time"),
        "loop_interval_minutes": data.get("loop_interval_minutes"),
        "test_mode": data.get("test_mode"),
        "test_target": data.get("test_target"),
        "settings": _settings_payload(options),
        "alexa": _alexa_payload(coordinator),
        "calendar": calendar,
        "entities": _entity_suggestions(hass),
    }


def _entity_suggestions(hass: HomeAssistant) -> dict[str, list[dict[str, str]]]:
    """Existing entities the panel can suggest for the entity pickers.

    Grouped by the option they belong to so the frontend can render a
    datalist per field without any extra round trip.
    """
    wanted = {
        "lights": ("light",),
        "media_players": ("media_player",),
        "calendars": ("calendar",),
        "notifiers": ("notify",),
        "input_text": ("input_text",),
        "input_boolean": ("input_boolean",),
    }
    suggestions: dict[str, list[dict[str, str]]] = {}
    for group, domains in wanted.items():
        items: list[dict[str, str]] = []
        for domain in domains:
            for state in hass.states.async_all(domain):
                name = state.attributes.get("friendly_name") or state.entity_id
                items.append({"id": state.entity_id, "name": str(name)})
        suggestions[group] = sorted(items, key=lambda item: item["id"])
    return suggestions


def _settings_payload(options: dict[str, Any]) -> dict[str, Any]:
    """Only the settings the panel is allowed to show and edit."""
    return {key: options.get(key) for key in EDITABLE_KEYS}


def _alexa_payload(coordinator: DacCoordinator) -> dict:
    """Status of the optional Alexa device-alarm bridge."""
    bridge = coordinator.alexa
    player = bridge.player
    helper_state = _state(coordinator.hass, bridge.helper)
    gate_state = _state(coordinator.hass, bridge.gate_boolean)
    return {
        "enabled": bridge.enabled,
        "player": player,
        "player_ok": bool(player) and _state(coordinator.hass, player) is not None,
        "helper": bridge.helper,
        "helper_ok": helper_state is not None,
        "gate": bridge.gate_boolean,
        "gate_ok": gate_state is not None,
        "gate_on": bool(gate_state) and gate_state.state == "on",
        "stored_alarm": bridge.stored_alarm(),
        "pre_alarm_minutes": bridge.pre_alarm_minutes,
        "stop_word": bridge.stop_word,
        "routine_name": ALEXA_ROUTINE_NAME,
    }


def _state(hass: HomeAssistant, entity_id: str):
    """Small helper so _alexa_payload stays easy to read."""
    return hass.states.get(entity_id)


async def _calendar_payload(hass: HomeAssistant, coordinator: DacCoordinator) -> dict:
    """Own + external vacation days for the month grid."""
    today = dt_util.now().date()
    start = today - timedelta(days=_CALENDAR_PAST_DAYS)
    end = today + timedelta(days=_CALENDAR_LOOKAHEAD_DAYS)
    keywords = vacation_keywords(coordinator.options)

    own_entity = _first_calendar(hass)
    own_days = await _own_vacation_days(hass, own_entity, start, end)
    own_by_date = {day["date"]: day for day in own_days}

    external_calendars = [
        cal
        for cal in (coordinator.options.get("vacation_calendars") or [])
        if cal != own_entity
    ]
    external_days: list[dict[str, Any]] = []
    if external_calendars:
        events = await _fetch_events(hass, external_calendars, start, end)
        seen: set[str] = set()
        for day in _expand_event_days(events):
            if day in own_by_date or day in seen:
                continue
            if not _day_is_vacation(events, day, keywords):
                continue
            seen.add(day)
            external_days.append({"date": day, "summary": _day_summary(events, day, keywords)})

    return {
        "entity_id": own_entity,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "own": own_days,
        "external": external_days,
    }


async def _own_vacation_days(
    hass: HomeAssistant, entity_id: str | None, start: date, end: date
) -> list[dict[str, Any]]:
    """Whole-day events stored on the DAC vacation calendar."""
    entity = _lookup_entity(hass, entity_id) if entity_id else None
    if entity is None:
        return []
    days: list[dict[str, Any]] = []
    for event in list(getattr(entity, "_events", [])):
        first = _parse_date(event.get("start"))
        last = _parse_date(event.get("end"))
        if first is None:
            continue
        # Stored all-day events use an exclusive end date.
        if last is None:
            last = first
        for day in _range_days(first.isoformat(), last.isoformat()):
            if day == last and last > first:
                continue
            if start <= day <= end:
                days.append(
                    {
                        "date": day.isoformat(),
                        "summary": event.get("summary") or "Urlaub",
                        "uid": event.get("uid"),
                    }
                )
    return days


async def _fetch_events(
    hass: HomeAssistant, calendars: list[str], start: date, end: date
) -> list[dict[str, Any]]:
    """Fetch raw events from the given calendars (empty list on failure)."""
    try:
        result = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": calendars,
                "start_date_time": dt_util.start_of_local_day(start).isoformat(),
                "end_date_time": dt_util.start_of_local_day(end).isoformat(),
            },
            blocking=True,
            return_response=True,
        )
    except (HomeAssistantError, ValueError) as err:
        _LOGGER.warning("DAC calendar fetch failed: %s", err)
        return []
    events: list[dict[str, Any]] = []
    for response in result.values():
        events.extend(response.get("events") or [])
    return events


def _expand_event_days(events: list[dict[str, Any]]) -> set[date]:
    """All days covered by the given events."""
    days: set[date] = set()
    for event in events:
        first = _parse_date(event.get("start"))
        last = _parse_date(event.get("end"))
        if first is None:
            continue
        if last is None or last < first:
            last = first
        for day in _range_days(first.isoformat(), last.isoformat()):
            days.add(day)
    return days


def _day_is_vacation(events: list[dict[str, Any]], day: date, keywords: tuple[str, ...]) -> bool:
    """True when any matching event marks this day as vacation/holiday."""
    return any(event_marks_vacation(event, day, keywords) for event in events)


def _day_summary(
    events: list[dict[str, Any]], day: date, keywords: tuple[str, ...]
) -> str:
    """Summary of the first matching event covering the given day."""
    for event in events:
        if event_marks_vacation(event, day, keywords) and event.get("summary"):
            return str(event["summary"])
    for event in events:
        first = _parse_date(event.get("start"))
        last = _parse_date(event.get("end")) or first
        if first is not None and last is not None and first <= day <= last:
            if event.get("summary"):
                return str(event["summary"])
    return "Urlaub"


class _Call:
    """Minimal ServiceCall stand-in for internal coordinator calls."""

    def __init__(self, data: dict) -> None:
        self.data = data
