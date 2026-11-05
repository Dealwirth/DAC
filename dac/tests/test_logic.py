"""Tests for the pure time/alarm logic of the DAC app.

These mirror the integration's tests so the app computes identical alarm times.
"""
from __future__ import annotations

from datetime import date, datetime, time

import pytest

from app.logic import (
    compute_alarm_time,
    default_resolution,
    event_marks_vacation,
    event_overlaps_day,
    format_alexa_time,
    next_occurrence,
    parse_time_str,
    split_am_pm,
)


def test_parse_time_str_accepts_seconds_and_short_form() -> None:
    assert parse_time_str("06:00") == time(6, 0)
    assert parse_time_str("06:00:30") == time(6, 0, 30)
    assert parse_time_str(time(7, 30)) == time(7, 30)


def test_parse_time_str_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        parse_time_str("nonsense")


def test_compute_alarm_time_subtracts_offset() -> None:
    assert compute_alarm_time(time(6, 45), 60) == time(5, 45)
    assert compute_alarm_time(time(6, 45), 0) == time(6, 45)


def test_compute_alarm_time_wraps_across_midnight() -> None:
    assert compute_alarm_time(time(0, 30), 60) == time(23, 30)


def test_alexa_helpers() -> None:
    assert format_alexa_time(time(5, 4, 59)) == "05:04"
    assert split_am_pm(time(5, 0)) == "morgens"
    assert split_am_pm(time(17, 0)) == "abends"


def test_next_occurrence_rolls_to_tomorrow() -> None:
    now = datetime(2026, 9, 6, 23, 0)
    assert next_occurrence(now, time(5, 0)) == datetime(2026, 9, 7, 5, 0)
    assert next_occurrence(now, time(23, 30)) == datetime(2026, 9, 6, 23, 30)


def test_default_resolution_commits_todays_alarm() -> None:
    now = datetime(2026, 9, 6, 5, 0)
    assert default_resolution(now, time(6, 0), time(21, 0)) == (date(2026, 9, 6), time(6, 0))


def test_default_resolution_waits_before_cutoff() -> None:
    now = datetime(2026, 9, 6, 19, 0)
    assert default_resolution(now, time(6, 0), time(21, 0)) == (None, None)


def test_default_resolution_commits_tomorrow_after_cutoff() -> None:
    now = datetime(2026, 9, 6, 21, 30)
    assert default_resolution(now, time(6, 0), time(21, 0)) == (date(2026, 9, 7), time(6, 0))


def test_event_overlaps_day() -> None:
    day = date(2026, 9, 6)
    assert event_overlaps_day(
        {"start": {"dateTime": "2026-09-06T08:00:00+02:00"},
         "end": {"dateTime": "2026-09-06T16:00:00+02:00"}}, day)
    # An event on a clearly later day does not overlap (the window ends at the
    # very end of the requested day).
    assert not event_overlaps_day(
        {"start": {"dateTime": "2026-09-08T08:00:00+02:00"},
         "end": {"dateTime": "2026-09-08T16:00:00+02:00"}}, day)


def test_event_marks_vacation_matches_keywords() -> None:
    day = date(2026, 9, 6)
    event = {"summary": "Urlaub Max", "start": {"date": "2026-09-06"}, "end": {"date": "2026-09-07"}}
    assert event_marks_vacation(event, day, ["urlaub", "feiertag"])
    assert not event_marks_vacation(event, day, ["feiertag"])


def test_event_marks_vacation_ignores_other_days() -> None:
    day = date(2026, 9, 8)
    event = {"summary": "Urlaub", "start": {"date": "2026-09-06"}, "end": {"date": "2026-09-07"}}
    assert not event_marks_vacation(event, day, ["urlaub"])
