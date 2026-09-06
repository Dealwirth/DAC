"""Unit tests for the pure DAC logic (no hass required)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from homeassistant.util import dt as dt_util

from custom_components.dac.logic import (
    compute_alarm_time,
    default_resolution,
    event_marks_vacation,
    event_overlaps_day,
    next_occurrence,
    parse_time_str,
)


def test_parse_time_str_passthrough_and_parse():
    assert parse_time_str(time(7, 30)) == time(7, 30)
    assert parse_time_str("06:00") == time(6, 0)
    assert parse_time_str("06:00:00") == time(6, 0)
    with pytest.raises(ValueError):
        parse_time_str("nonsense")


def test_compute_alarm_time_basic_offset():
    # Work start 08:00, 60 min offset -> alarm at 07:00
    assert compute_alarm_time(time(8, 0), 60) == time(7, 0)
    # 25 min offset
    assert compute_alarm_time(time(8, 0), 25) == time(7, 35)


def test_compute_alarm_time_wraps_midnight():
    # Work start 00:30 with 60 min offset wraps to 23:30 (previous day)
    assert compute_alarm_time(time(0, 30), 60) == time(23, 30)
    # Work start 05:00 with 300 min offset wraps to 00:00
    assert compute_alarm_time(time(5, 0), 300) == time(0, 0)


def test_next_occurrence_today_and_tomorrow():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 9, 6, 10, 0, tzinfo=tz)
    # 12:00 is still ahead today
    assert next_occurrence(now, time(12, 0)) == datetime(2026, 9, 6, 12, 0, tzinfo=tz)
    # 06:00 already passed -> tomorrow
    assert next_occurrence(now, time(6, 0)) == datetime(2026, 9, 7, 6, 0, tzinfo=tz)
    # exactly now -> tomorrow (avoids firing immediately)
    exact = datetime(2026, 9, 6, 12, 0, tzinfo=tz)
    assert next_occurrence(exact, time(12, 0)) == datetime(2026, 9, 7, 12, 0, tzinfo=tz)


def test_default_resolution_today_still_ahead():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 9, 6, 3, 0, tzinfo=tz)  # default 06:00 still ahead
    day, t = default_resolution(now, time(6, 0), time(20, 30))
    assert (day, t) == (date(2026, 9, 6), time(6, 0))


def test_default_resolution_awaiting_input_before_cutoff():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 9, 6, 12, 0, tzinfo=tz)  # default passed, cutoff not reached
    day, t = default_resolution(now, time(6, 0), time(20, 30))
    assert (day, t) == (None, None)


def test_default_resolution_tomorrow_after_cutoff():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 9, 6, 21, 0, tzinfo=tz)  # after cutoff -> tomorrow
    day, t = default_resolution(now, time(6, 0), time(20, 30))
    assert (day, t) == (date(2026, 9, 7), time(6, 0))


def test_default_resolution_no_cutoff_schedules_tomorrow():
    tz = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 9, 6, 12, 0, tzinfo=tz)
    day, t = default_resolution(now, time(6, 0), None)
    assert (day, t) == (date(2026, 9, 7), time(6, 0))


def _event(summary: str, start: datetime, end: datetime) -> dict:
    return {
        "summary": summary,
        "start": {"date_time": start.isoformat()},
        "end": {"date_time": end.isoformat()},
    }


TZ = ZoneInfo("Europe/Berlin")


def test_event_overlaps_day():
    day = date(2026, 9, 6)
    ev = _event(
        "Arbeit",
        datetime(2026, 9, 6, 22, 0, tzinfo=TZ),
        datetime(2026, 9, 7, 6, 0, tzinfo=TZ),
    )
    assert event_overlaps_day(ev, day)
    assert event_overlaps_day(ev, date(2026, 9, 7))
    ev_later = _event(
        "Arbeit",
        datetime(2026, 9, 8, 8, 0, tzinfo=TZ),
        datetime(2026, 9, 8, 17, 0, tzinfo=TZ),
    )
    assert not event_overlaps_day(ev_later, day)


def test_event_marks_vacation_by_keyword():
    day = date(2026, 9, 6)
    vac = _event(
        "Urlaub Mallorca",
        datetime(2026, 9, 6, 0, 0, tzinfo=TZ),
        datetime(2026, 9, 7, 0, 0, tzinfo=TZ),
    )
    assert event_marks_vacation(vac, day)
    work = _event(
        "Frühdienst",
        datetime(2026, 9, 6, 6, 0, tzinfo=TZ),
        datetime(2026, 9, 6, 14, 0, tzinfo=TZ),
    )
    assert not event_marks_vacation(work, day)


def test_event_marks_vacation_all_day_events():
    day = date(2026, 12, 25)
    ev = {
        "summary": "1. Weihnachtsfeiertag",
        "start": {"date": "2026-12-25"},
        "end": {"date": "2026-12-26"},
    }
    assert event_marks_vacation(ev, day)


def test_event_marks_vacation_description_counts():
    day = date(2026, 9, 6)
    ev = _event(
        "Tag X",
        datetime(2026, 9, 6, 0, 0, tzinfo=TZ),
        datetime(2026, 9, 7, 0, 0, tzinfo=TZ),
    )
    ev["description"] = "Feiertag laut Dienstplan"
    assert event_marks_vacation(ev, day)
