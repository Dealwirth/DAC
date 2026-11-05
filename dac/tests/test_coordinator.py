"""Tests for the DAC app coordinator (state machine + scheduler)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.config import settings
from app.coordinator import (
    MODE_DISMISSED,
    MODE_STANDARD,
    MODE_VACATION,
    STATE_IDLE,
    STATE_RINGING,
    STATE_STOPPED,
    Coordinator,
)


def _coordinator(monkeypatch, now: datetime) -> Coordinator:
    """A coordinator whose clock is frozen at ``now``."""
    import app.coordinator as module

    monkeypatch.setattr(module, "_now", lambda: now)
    return Coordinator()


async def test_set_work_time_schedules_offset_alarm(monkeypatch, fake_ha) -> None:
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "")
    settings.update({"offset_minutes": 60, "alexa_media_player": "media_player.echo"})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)

    await c.set_work_time("06:45")

    # 19:00 is past the 21:00-independent cutoff? No: 19:00 < 21:00, so the
    # work time belongs to *today* -> the alarm was already in the past and
    # rolls to tomorrow.
    assert c._alarm_time == time(6, 45)
    assert c._alarm_target is not None
    assert c.snapshot()["alarm_time"] == "06:45"
    assert c.desired_alarm_text() == "05:43"  # 05:45 minus 2 min pre-alarm


async def test_evening_work_time_targets_tomorrow(monkeypatch, fake_ha) -> None:
    settings.update({"offset_minutes": 60, "reminder_time": "21:00"})
    now = datetime(2026, 11, 5, 22, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.set_work_time("06:45")
    assert c._work_time_day == date(2026, 11, 6)
    assert c._alarm_day == date(2026, 11, 6)


async def test_clear_work_time_falls_back_to_default(monkeypatch, fake_ha) -> None:
    settings.update({"offset_minutes": 60, "default_alarm_time": "06:00"})
    now = datetime(2026, 11, 5, 22, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.set_work_time("06:45")
    await c.clear_work_time()
    assert c._work_time is None
    # After the cutoff the default alarm is committed for tomorrow.
    assert c._alarm_time == time(6, 0)
    assert c._alarm_day == date(2026, 11, 6)


async def test_default_alarm_waits_before_cutoff(monkeypatch, fake_ha) -> None:
    settings.update({"default_alarm_time": "06:00", "reminder_time": "21:00"})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    c.reschedule()
    assert c._state == STATE_IDLE
    assert c._alarm_target is None


async def test_dismiss_today_sets_mode_and_clears_alarm(monkeypatch, fake_ha) -> None:
    settings.update({"offset_minutes": 60})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.set_work_time("06:45")
    await c.dismiss_for_today()
    assert c.current_mode == MODE_DISMISSED
    assert c.desired_alarm_text() is None


async def test_standard_mode_reenables_alarm(monkeypatch, fake_ha) -> None:
    settings.update({"offset_minutes": 60, "default_alarm_time": "06:00"})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.dismiss_for_today()
    await c.set_mode(MODE_STANDARD)
    assert c.current_mode == MODE_STANDARD


async def test_vacation_mode_pauses_alarm(monkeypatch, fake_ha) -> None:
    settings.update({"offset_minutes": 60})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.set_work_time("06:45")
    await c.set_mode(MODE_VACATION)
    assert c.current_mode == MODE_VACATION
    assert c._state == "vacation"
    assert c.desired_alarm_text() is None


async def test_vacation_from_calendar(monkeypatch, fake_ha) -> None:
    settings.update({"vacation_calendars": ["calendar.urlaub"], "vacation_keywords": "urlaub"})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)

    async def fake_call(domain, service, data, **kwargs):
        assert domain == "calendar"
        return {"calendar.urlaub": {"events": [
            {"summary": "Urlaub", "start": {"date": "2026-11-05"}, "end": {"date": "2026-11-06"}},
        ]}}

    monkeypatch.setattr("app.ha_client.ha.call_service", fake_call)
    await c.refresh_vacation()
    assert c._is_vacation is True
    assert c._state == "vacation"


async def test_test_alarm_rings_and_stops(monkeypatch, fake_ha) -> None:
    settings.update({"alexa_media_player": "media_player.echo", "alarm_lights": ["light.sz"]})
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "")
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.start_test_alarm(1)
    assert c.test_mode_active

    import app.coordinator as module

    monkeypatch.setattr(module, "_now", lambda: now + timedelta(minutes=2))
    await c.tick()
    assert c._state == STATE_RINGING
    assert fake_ha.calls_for("light", "turn_on")

    await c.stop_alarm()
    assert c._state == STATE_IDLE
    assert fake_ha.calls_for("input_boolean", "turn_off")


async def test_stop_alarm_marks_day_stopped(monkeypatch, fake_ha) -> None:
    settings.update({"alexa_media_player": "media_player.echo"})
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    now = datetime(2026, 11, 5, 5, 45).astimezone()
    c = _coordinator(monkeypatch, now)
    c._set_state(STATE_RINGING)
    c._ring_started = now
    await c.stop_alarm()
    assert c._state == STATE_STOPPED
    assert now.date() in c._stopped_days


async def test_safety_cap_stops_long_ringing(monkeypatch, fake_ha) -> None:
    settings.update({"max_ring_minutes": 30, "alexa_media_player": "media_player.echo"})
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    now = datetime(2026, 11, 5, 5, 45).astimezone()
    c = _coordinator(monkeypatch, now)
    c._set_state(STATE_RINGING)
    c._ring_started = now - timedelta(minutes=31)

    import app.coordinator as module

    monkeypatch.setattr(module, "_now", lambda: now)
    await c.tick()
    assert c._state == STATE_STOPPED


async def test_reminder_fires_without_work_time(monkeypatch, fake_ha) -> None:
    settings.update({"reminder_time": "21:00", "notifier": "notify.handy", "default_alarm_time": "06:00"})
    now = datetime(2026, 11, 5, 21, 5).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.tick()
    assert fake_ha.calls_for("notify", "handy")
    # Only once per day.
    before = len(fake_ha.calls)
    await c.tick()
    assert len(fake_ha.calls) == before


async def test_reminder_skipped_when_work_time_set(monkeypatch, fake_ha) -> None:
    settings.update({"reminder_time": "21:00", "notifier": "notify.handy"})
    now = datetime(2026, 11, 5, 21, 5).astimezone()
    c = _coordinator(monkeypatch, now)
    c._work_time_day = date(2026, 11, 6)
    await c.tick()
    assert not fake_ha.calls_for("notify", "handy")


async def test_snapshot_serialisable(monkeypatch, fake_ha) -> None:
    import json

    settings.update({"offset_minutes": 60})
    now = datetime(2026, 11, 5, 19, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.set_work_time("06:45")
    json.dumps(c.snapshot())  # must not raise


async def test_state_persists_and_restores(monkeypatch, fake_ha) -> None:
    settings.update({"offset_minutes": 60})
    now = datetime(2026, 11, 5, 22, 0).astimezone()
    c = _coordinator(monkeypatch, now)
    await c.set_work_time("06:45")
    await c.save_state()

    c2 = _coordinator(monkeypatch, now)
    await c2.restore_state()
    assert c2._work_time == time(6, 45)
    assert c2._work_time_day == date(2026, 11, 6)
