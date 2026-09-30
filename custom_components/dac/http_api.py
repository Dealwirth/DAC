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
    """REST-ish API under /api/dac used by the DAC dashboard card."""

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
        """Execute an action: set_work_time / stop / dismiss / mode / vacation."""
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
                time_value = body.get("time")
                if not time_value:
                    return self.json_message("missing time", 400)
                call = _FakeCall({"time": time_value})
                await coordinator._async_set_work_time_impl(call)
                await coordinator.async_save_state()
                await coordinator.alexa.async_sync()
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
    entity-id prefix so the dashboard keeps working in odd setups.
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
    entity = _lookup_entity(hass, entity_id)
    if entity is None or not hasattr(entity, "async_delete_event"):
        raise HomeAssistantError("Calendar entity not found")
    await entity.async_delete_event(uid)


def _lookup_entity(hass: HomeAssistant, entity_id: str):
    """Find a live entity object by its entity id.

    ``hass.data["domain_entities"]`` maps ``domain -> {entity_id: Entity}`` and
    is the documented internal index (populated in ``EntityPlatform.__init__``).
    The ``entity_platform`` mapping (``domain -> [EntityPlatform, ...]``) is used
    as a fallback so the lookup survives internal reshuffles.
    """
    domain = entity_id.split(".", 1)[0]
    domain_entities = hass.data.get("domain_entities") or {}
    entity = (domain_entities.get(domain) or {}).get(entity_id)
    if entity is not None:
        return entity

    for platform_list in (hass.data.get("entity_platform") or {}).values():
        for platform in platform_list:
            getter = getattr(platform, "get_entity", None)
            if getter is None:
                continue
            entity = getter(entity_id)
            if entity is not None:
                return entity
    return None


async def _entry_payload(hass: HomeAssistant, coordinator: DacCoordinator) -> dict:
    """Build the dashboard payload for one DAC entry."""
    data = coordinator.data
    calendar_events = await _vacation_events(hass, 14)
    return {
        "entry_id": coordinator.entry_id,
        "state": data.get("state"),
        "mode": data.get("mode"),
        "vacation": data.get("vacation"),
        "work_time": data.get("work_time"),
        "alexa": _alexa_payload(coordinator),
        "work_time_day": data.get("work_time_day"),
        "alarm_time": data.get("alarm_time"),
        "alarm_day": data.get("alarm_day"),
        "alarm_target": data.get("alarm_target"),
        "offset_minutes": data.get("offset_minutes"),
        "default_alarm_time": data.get("default_alarm_time"),
        "vacation_events": calendar_events,
    }


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
    }


def _state(hass: HomeAssistant, entity_id: str):
    """Small helper so _alexa_payload stays easy to read."""
    return hass.states.get(entity_id)


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
