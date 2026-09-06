"""Calendar platform for DAC – the DAC vacation calendar (Urlaubskalender)."""
from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
import random
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEVICE_NAME, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the DAC vacation calendar."""
    async_add_entities([DacVacationCalendar(hass, entry)])


class DacVacationCalendar(CalendarEntity):
    """A user-editable vacation calendar backed by Home Assistant storage."""

    _attr_translation_key = "vacation_calendar"
    _attr_name = "DAC Urlaubskalender"
    _attr_unique_id = f"{DOMAIN}_vacation_calendar"
    _attr_has_entity_name = False
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT
        | CalendarEntityFeature.DELETE_EVENT
        | CalendarEntityFeature.UPDATE_EVENT
    )

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize entity and load stored events."""
        self.hass = hass
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=DEVICE_NAME,
            manufacturer="Dealwirth",
            entry_type=DeviceEntryType.SERVICE,
        )
        self._events: list[dict[str, Any]] = []
        self._store: Store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.calendar")
        self._loaded = False

    async def async_added_to_hass(self) -> None:
        """Load persisted events."""
        await super().async_added_to_hass()
        data = await self._store.async_load() or {}
        self._events = list(data.get("events") or [])
        self._loaded = True
        self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Persist events on removal."""
        await self._async_save()

    async def _async_save(self) -> None:
        await self._store.async_save({"events": self._events})

    # -------------------------------------------------------- CalendarEntity
    @property
    def event(self) -> CalendarEvent | None:
        """The event happening right now."""
        now = dt_util.now()
        for ev in self._events:
            start = _parse(ev["start"])
            end = _parse(ev["end"])
            if start and end and start <= now <= end:
                return _to_calendar_event(ev)
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return all events overlapping the given range."""
        result: list[CalendarEvent] = []
        for ev in self._events:
            start = _parse(ev["start"])
            end = _parse(ev["end"])
            if start and end and start <= end_date and end >= start_date:
                result.append(_to_calendar_event(ev))
        return result

    async def async_create_event(self, **kwargs: Any) -> None:
        """Create a vacation event (UI calendar editor compatible)."""
        start = kwargs["dtstart"]
        end = kwargs["dtend"]
        self._events.append(
            {
                "uid": f"{dt_util.now().timestamp():.0f}-{random.randint(100, 999)}",
                "summary": kwargs["summary"],
                "start": _serialize(start),
                "end": _serialize(end),
                "description": kwargs.get("description") or "",
            }
        )
        await self._async_save()
        self.async_write_ha_state()

    async def async_delete_event(
        self, uid: str, recurrence_id: str | None = None, recurrence_range: str | None = None
    ) -> None:
        """Delete an event by uid."""
        self._events = [ev for ev in self._events if ev.get("uid") != uid]
        await self._async_save()
        self.async_write_ha_state()

    async def async_update_event(
        self,
        uid: str,
        event: dict[str, Any],
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        """Update an event (drag & drop in the calendar editor)."""
        for ev in self._events:
            if ev.get("uid") == uid:
                ev["summary"] = event.get("summary") or ev["summary"]
                ev["description"] = event.get("description") or ""
                ev["start"] = _serialize(event["start"])
                ev["end"] = _serialize(event["end"])
        await self._async_save()
        self.async_write_ha_state()


# --------------------------------------------------------------------- utils
def _parse(value: str | dict | datetime | date) -> datetime | None:
    """Parse a stored event boundary."""
    if isinstance(value, datetime):
        return dt_util.as_local(value)
    if isinstance(value, str):
        try:
            if len(value) == 10:
                return datetime.combine(
                    date.fromisoformat(value), dt_time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE
                )
            return dt_util.parse_datetime(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        raw = value.get("date_time") or value.get("date")
        return _parse(raw) if raw else None
    return None


def _serialize(value: datetime | date) -> str:
    """Serialize an event boundary for storage."""
    if isinstance(value, datetime):
        return dt_util.as_local(value).isoformat()
    return value.isoformat()


def _to_calendar_event(ev: dict[str, Any]) -> CalendarEvent:
    """Convert a stored event into a CalendarEvent."""
    start = _parse(ev["start"])
    end = _parse(ev["end"])
    all_day = len(str(ev["start"])) == 10
    return CalendarEvent(
        start=start.date() if all_day else start,
        end=end.date() if all_day else end,
        summary=ev["summary"],
        description=ev.get("description") or None,
        uid=ev.get("uid"),
    )
