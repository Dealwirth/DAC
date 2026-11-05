"""Pure time/alarm logic for DAC – no Home Assistant objects needed.

This is a 1:1 port of the integration's ``logic.py`` so the app and the former
HACS integration compute exactly the same alarm times.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

ALEXA_SET_TEXT = "stelle einen Wecker auf {time} Uhr {tod}"
ALEXA_SET_NAMED_TEXT = "stelle einen Wecker auf {time} Uhr {tod} namens {label}"
ALEXA_CLEAR_TEXT = "lösche den Wecker um {time} Uhr"


def split_am_pm(value: time) -> str:
    """Return 'morgens' or 'abends' for a 24h time (hour < 12 -> morgens)."""
    return "morgens" if value.hour < 12 else "abends"


def format_alexa_time(value: time) -> str:
    """Format a time like '05:00' (seconds dropped) for Alexa commands."""
    return f"{value.hour:02d}:{value.minute:02d}"


def parse_time_str(value: str | time) -> time:
    """Parse a time from a string like '06:00' / '06:00:00' (or pass through)."""
    if isinstance(value, time):
        return value
    text = str(value).strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Invalid time string: {value!r}")


def parse_date_str(value: str | date) -> date:
    """Parse a date from an ISO string like '2026-09-06' (or pass through)."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def compute_alarm_time(work_start: time, offset_minutes: int) -> time:
    """Subtract the offset from the work start time and return the alarm time.

    The result is normalized into 00:00..23:59; a work start before the offset
    (e.g. 00:30 with 60 min offset) wraps around to the previous day.
    """
    base = datetime.combine(date(2000, 1, 2), work_start)
    return (base - timedelta(minutes=offset_minutes)).time()


def next_occurrence(now: datetime, alarm_time: time) -> datetime:
    """Return the next datetime where the clock shows ``alarm_time``."""
    candidate = datetime.combine(now.date(), alarm_time, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def default_resolution(
    now: datetime, default_time: time, cutoff: time | None
) -> tuple[date | None, time | None]:
    """Default-alarm fallback: awaiting input until the cutoff passes."""
    candidate_today = datetime.combine(now.date(), default_time, tzinfo=now.tzinfo)
    if candidate_today > now:
        return now.date(), default_time
    if cutoff is None or now.time() >= cutoff:
        return now.date() + timedelta(days=1), default_time
    return None, None


def event_overlaps_day(event: dict[str, Any], day: date) -> bool:
    """Return True if a calendar event overlaps the given day."""
    start = _event_dt(event.get("start"))
    end = _event_dt(event.get("end"))
    if start is None or end is None:
        return False
    day_start = datetime.combine(day, time.min, tzinfo=start.tzinfo)
    day_end = datetime.combine(day + timedelta(days=1), time.max, tzinfo=start.tzinfo)
    return start <= day_end and end >= day_start


def event_marks_vacation(
    event: dict[str, Any], day: date, keywords: tuple[str, ...] | list[str]
) -> bool:
    """Return True if a calendar event marks the day as vacation/holiday."""
    if not event_overlaps_day(event, day):
        return False
    haystack = " ".join(
        str(event.get(key, "") or "") for key in ("summary", "title", "description")
    ).lower()
    return any(keyword.lower() in haystack for keyword in keywords if keyword)


def _event_dt(value: Any) -> datetime | None:
    """Convert a calendar event start/end dict into a datetime."""
    if not isinstance(value, dict):
        return None
    raw = value.get("dateTime") or value.get("date_time") or value.get("date")
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_local_tz())
    return parsed


def _local_tz():
    """The local timezone (avoids importing Home Assistant helpers)."""

    return datetime.now().astimezone().tzinfo or UTC
