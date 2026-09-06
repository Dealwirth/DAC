"""Pure time/alarm logic for DAC – no Home Assistant objects needed (unit-testable)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.util import dt as dt_util

DEFAULT_VACATION_KEYWORDS: tuple[str, ...] = (
    "urlaub",
    "urlaubstag",
    "feiertag",
    "ferien",
    "vacation",
    "holiday",
)


def parse_time_str(value: str | time) -> time:
    """Parse a time from a string like '06:00' / '06:00:00' (or pass through)."""
    if isinstance(value, time):
        return value
    parsed = dt_util.parse_time(str(value))
    if parsed is None:
        raise ValueError(f"Invalid time string: {value!r}")
    return parsed


def parse_date_str(value: str | date) -> date:
    """Parse a date from an ISO string like '2026-09-06' (or pass through)."""
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def compute_alarm_time(work_start: time, offset_minutes: int) -> time:
    """Subtract the offset from the work start time and return the alarm time.

    The result is normalized into 00:00..23:59; a work start before the offset
    (e.g. 00:30 with 60 min offset) wraps around to the previous day.
    """
    base = datetime.combine(date(2000, 1, 2), work_start)
    alarm_dt = base - timedelta(minutes=offset_minutes)
    return alarm_dt.time()


def next_occurrence(now: datetime, alarm_time: time) -> datetime:
    """Return the next datetime where the clock shows ``alarm_time``."""
    candidate = datetime.combine(now.date(), alarm_time, tzinfo=now.tzinfo)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def default_resolution(
    now: datetime, default_time: time, cutoff: time | None
) -> tuple[date | None, time | None]:
    """Default-alarm fallback: awaiting input until the cutoff passes.

    Returns ``(day, alarm_time)`` or ``(None, None)`` while awaiting input:

    * today's default alarm still ahead -> it is already committed -> today
    * today's default passed and the cutoff reached -> tomorrow
    * today's default passed but cutoff not reached -> awaiting (the reminder
      asks the user; nothing is scheduled yet)
    """
    candidate_today = datetime.combine(now.date(), default_time, tzinfo=now.tzinfo)
    if candidate_today > now:
        return now.date(), default_time
    if cutoff is None or now.time() >= cutoff:
        return now.date() + timedelta(days=1), default_time
    return None, None


def event_overlaps_day(event: dict[str, Any], day: date) -> bool:
    """Return True if a calendar.get_events result overlaps the given day."""
    start = _event_dt(event.get("start"))
    end = _event_dt(event.get("end"))
    if start is None or end is None:
        return False
    day_start = datetime.combine(day, time.min, tzinfo=start.tzinfo)
    day_end = datetime.combine(day + timedelta(days=1), time.max, tzinfo=start.tzinfo)
    return start <= day_end and end >= day_start


def event_marks_vacation(
    event: dict[str, Any],
    day: date,
    keywords: tuple[str, ...] = DEFAULT_VACATION_KEYWORDS,
) -> bool:
    """Return True if a calendar event marks the day as vacation/holiday."""
    if not event_overlaps_day(event, day):
        return False
    haystack = " ".join(
        str(event.get(key, "") or "") for key in ("summary", "title", "description")
    ).lower()
    return any(keyword.lower() in haystack for keyword in keywords)


def _event_dt(value: Any) -> datetime | None:
    """Convert a calendar event start/end dict into a datetime."""
    if not isinstance(value, dict):
        return None
    if "date_time" in value:
        raw = value["date_time"]
        if isinstance(raw, datetime):
            return dt_util.as_local(raw)
        parsed = dt_util.parse_datetime(str(raw))
        return dt_util.as_local(parsed) if parsed else None
    if "date" in value:
        try:
            parsed_date = parse_date_str(value["date"])
        except ValueError:
            return None
        return datetime.combine(parsed_date, time.min, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    return None
