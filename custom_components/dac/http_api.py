"""HTTP API endpoints for the DAC dashboard (no external dependencies)."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import DacCoordinator

_LOGGER = logging.getLogger(__name__)


class DacApiView(HomeAssistantView):
    """REST-ish API under /api/dac for the custom panel."""

    url = "/api/dac"
    name = "api:dac"
    requires_auth = True

    async def get(self, request) -> None:
        """Return the full dashboard state."""
        hass = request.app["hass"]
        payload = {"entries": []}
        for coordinator in _coordinators(hass):
            payload["entries"].append(await _entry_payload(hass, coordinator))
        return self.json(payload)

    async def post(self, request) -> None:
        """Execute an action: set_work_time / stop / dismiss / mode."""
        hass = request.app["hass"]
        try:
            body = await request.json()
        except ValueError:
            return self.json_message("invalid json", 400)
        action = body.get("action")
        coordinators = _coordinators(hass)
        if not coordinators:
            return self.json_message("no dac entry configured", 404)
        coordinator = coordinators[0]

        try:
            if action == "set_work_time":
                time_value = body.get("time")
                if not time_value:
                    return self.json_message("missing time", 400)
                call = _FakeCall({"time": time_value})
                await coordinator._async_set_work_time_impl(call)
                await coordinator.async_save_state()
            elif action == "stop":
                await coordinator.async_stop_alarm(_FakeCall({}))
            elif action == "dismiss":
                await coordinator._async_dismiss_for(dt_util.now().date())
            elif action == "mode":
                await coordinator.async_set_mode(body.get("mode", "standard"))
            elif action == "add_vacation":
                await _add_vacation(hass, body)
            elif action == "remove_vacation":
                await _remove_vacation(hass, body)
            else:
                return self.json_message(f"unknown action: {action}", 400)
        except (HomeAssistantError, ValueError) as err:
            return self.json_message(str(err), 400)
        return self.json({"ok": True})


def _coordinators(hass: HomeAssistant) -> list[DacCoordinator]:
    return list((hass.data.get(DOMAIN) or {}).values())


def _first_calendar(hass: HomeAssistant):
    """Find the first DAC vacation calendar entity."""
    for state in hass.states.async_all("calendar"):
        if state.entity_id.startswith("calendar.dac"):
            return state.entity_id
    return None


async def _add_vacation(hass: HomeAssistant, body: dict) -> None:
    """Create a vacation event on the DAC vacation calendar."""
    entity_id = _first_calendar(hass)
    if not entity_id:
        raise HomeAssistantError("No DAC vacation calendar found")
    summary = body.get("summary") or "Urlaub"
    start = body.get("start")
    end = body.get("end")
    if not start or not end:
        raise HomeAssistantError("start and end are required")
    await hass.services.async_call(
        "calendar",
        "create_event",
        {
            "entity_id": entity_id,
            "summary": summary,
            "start_date_time": start,
            "end_date_time": end,
            "description": body.get("description") or "",
        },
        blocking=True,
    )


async def _remove_vacation(hass: HomeAssistant, body: dict) -> None:
    """Delete a vacation event by uid from the DAC vacation calendar."""
    entity_id = _first_calendar(hass)
    if not entity_id:
        raise HomeAssistantError("No DAC vacation calendar found")
    uid = body.get("uid")
    if not uid:
        raise HomeAssistantError("uid required")
    platform = hass.data.get("calendar")
    # Fallback: call the entity method directly through the entity platform.
    component = hass.data.get("calendar") or {}
    entity = None
    if hasattr(component, "get_entity"):
        entity = component.get_entity(entity_id)
    if entity is None:
        entity = _lookup_entity(hass, entity_id)
    if entity is None or not hasattr(entity, "async_delete_event"):
        raise HomeAssistantError("Calendar entity not found")
    await entity.async_delete_event(uid)


def _lookup_entity(hass: HomeAssistant, entity_id: str):
    """Find an entity object via the entity platform registry."""
    for entry_platform in hass.data.get("entity_platform", {}).values():
        try:
            entity = entry_platform.get_entity(entity_id)
        except (AttributeError, KeyError):
            entity = None
        if entity is not None:
            return entity
    return None


async def _entry_payload(hass: HomeAssistant, coordinator: DacCoordinator) -> dict:
    """Build the dashboard payload for one DAC entry."""
    data = coordinator.data
    calendar_events = await _vacation_events(hass, 14)
    return {
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
        "vacation_events": calendar_events,
    }


async def _vacation_events(hass: HomeAssistant, days: int) -> list[dict]:
    """Fetch upcoming events from the DAC vacation calendar."""
    entity_id = _first_calendar(hass)
    if not entity_id:
        return []
    start = dt_util.start_of_local_day()
    end = start + timedelta(days=days)
    try:
        result = await hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": entity_id,
                "start_date_time": start.isoformat(),
                "end_date_time": end.isoformat(),
            },
            blocking=True,
            return_response=True,
        )
    except (HomeAssistantError, ValueError):
        return []
    events: list[dict] = []
    for response in result.values():
        for ev in response.get("events") or []:
            events.append(
                {
                    "uid": ev.get("uid") or "",
                    "summary": ev.get("summary") or "",
                    "start": str(ev.get("start")),
                    "end": str(ev.get("end")),
                }
            )
    return events



class _FakeCall:
    """Minimal ServiceCall stand-in for internal coordinator calls."""

    def __init__(self, data: dict) -> None:
        self.data = data
