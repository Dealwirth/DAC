"""Tests for the DacCoordinator alarm state machine."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.dac.const import (
    MODE_DISMISSED,
    MODE_STANDARD,
    MODE_VACATION,
    STATE_DISMISSED,
    STATE_IDLE,
    STATE_RINGING,
    STATE_SCHEDULED,
    STATE_STOPPED,
    STATE_VACATION,
)
from custom_components.dac.coordinator import DacCoordinator

TZ = "Europe/Berlin"

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _fake_call(data: dict):
    from tests.conftest import FakeCall

    return FakeCall(data)


async def _advance_to_alarm(hass: HomeAssistant, coordinator: DacCoordinator) -> None:
    """Fire the scheduled alarm trigger manually (deterministic, no wall clock)."""
    assert coordinator._alarm_target is not None
    await coordinator._alarm_fired(dt_util.now())


# ---------------------------------------------------------------------------
# tests: scheduling basics
# ---------------------------------------------------------------------------


# NOTE: freeze_time strings are UTC (Berlin = UTC+2 in September).

@freeze_time("2026-09-06 05:00:00")
async def test_manual_work_time_schedules_alarm_with_offset(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """Work start 15:00, offset 60 min -> alarm target 14:00 today."""
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))

    assert coordinator._state == STATE_SCHEDULED
    assert coordinator._alarm_time is not None and coordinator._alarm_time.strftime("%H:%M") == "15:00"
    target_local = dt_util.as_local(coordinator._alarm_target)
    assert target_local.strftime("%H:%M") == "14:00"
    assert coordinator._alarm_day == dt_util.now().date()


@freeze_time("2026-09-06 19:00:00")
async def test_evening_scan_targets_tomorrow(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """A scan at 21:00 (after cutoff 20:30) is for the next day."""
    await coordinator.async_set_work_time(_fake_call({"time": "08:00"}))

    assert coordinator._work_time_day == dt_util.now().date() + timedelta(days=1)
    target_local = dt_util.as_local(coordinator._alarm_target)
    assert target_local.date() == dt_util.now().date() + timedelta(days=1)
    assert target_local.strftime("%H:%M") == "07:00"


@freeze_time("2026-09-06 05:00:00")
async def test_default_fallback_used_without_work_time(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """No manual time, cutoff later -> default alarm 06:00 tomorrow? No:
    today's 06:00 default already passed and cutoff (20:30) not reached,
    so nothing is scheduled (awaiting input)."""
    coordinator._reschedule_alarm()

    assert coordinator._state == STATE_IDLE
    assert coordinator._alarm_target is None


@freeze_time("2026-09-06 01:00:00")
async def test_default_fallback_before_default_time(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """At 03:00 (Berlin) the 06:00 default still applies today."""
    coordinator._reschedule_alarm()

    assert coordinator._state == STATE_SCHEDULED
    assert coordinator._alarm_time.strftime("%H:%M") == "06:00"
    assert coordinator._alarm_day == dt_util.now().date()


# ---------------------------------------------------------------------------
# tests: alarm loop
# ---------------------------------------------------------------------------


@freeze_time("2026-09-06 11:59:59")
async def test_alarm_fires_loop_and_stop(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
):
    """Reaching the alarm time turns the lights on and the loop stops on stop."""
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    await _advance_to_alarm(hass, coordinator)

    assert coordinator._state == STATE_RINGING
    assert any(d == "light" and s == "turn_on" for d, s, _ in recorded)

    await coordinator.async_stop_alarm(_fake_call({}))
    assert coordinator._state == STATE_STOPPED
    # after stop, no new loop ticks fire
    n_before = len(recorded)
    await coordinator._loop_tick(dt_util.now())
    assert len(recorded) == n_before


@freeze_time("2026-09-06 11:59:59")
async def test_stop_alarm_while_not_ringing_is_harmless(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
):
    await coordinator.async_stop_alarm(_fake_call({}))
    assert coordinator._state != STATE_RINGING


# ---------------------------------------------------------------------------
# tests: Alexa gate (YAML Tag 1 / Tag 4 parity)
# ---------------------------------------------------------------------------


async def _gate_calls(hass: HomeAssistant, coordinator: DacCoordinator) -> list[str]:
    """Capture input_boolean service calls made while an action runs."""
    from unittest.mock import patch

    calls: list[str] = []
    registry_cls = type(hass.services)
    real_call = registry_cls.async_call

    async def spy(self, domain, service, service_data=None, **kwargs):
        if domain == "input_boolean":
            calls.append(service)
            return None
        return await real_call(self, domain, service, service_data, **kwargs)

    with patch.object(registry_cls, "async_call", autospec=True, side_effect=spy):
        await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
        await hass.async_block_till_done()
        await _advance_to_alarm(hass, coordinator)
        await hass.async_block_till_done()
        await coordinator.async_stop_alarm(_fake_call({}))
        await hass.async_block_till_done()
    return calls


@freeze_time("2026-09-06 11:59:59")
async def test_gate_turns_on_when_scheduled_and_off_when_stopped(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """Scheduling turns wecker_aktiv on, stopping the ringing alarm off."""
    from custom_components.dac.const import CONF_ALEXA_ENABLED

    coordinator._options[CONF_ALEXA_ENABLED] = True
    calls = await _gate_calls(hass, coordinator)
    assert "turn_on" in calls
    assert "turn_off" in calls


@freeze_time("2026-09-06 11:59:59")
async def test_gate_untouched_without_alexa(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """Without the Alexa bridge DAC never touches the user's helper."""
    calls = await _gate_calls(hass, coordinator)
    assert calls == []


# ---------------------------------------------------------------------------
# tests: dismissal
# ---------------------------------------------------------------------------


@freeze_time("2026-09-06 05:00:00")
async def test_dismiss_for_today_blocks_alarm(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    assert coordinator._alarm_target is not None

    await coordinator.async_dismiss_for_today(_fake_call({}))

    assert dt_util.now().date() in coordinator._dismissed_days
    # The scheduled alarm for today is gone entirely.
    assert coordinator._state == STATE_DISMISSED
    assert coordinator._alarm_target is None
    assert coordinator.current_mode == MODE_DISMISSED


@freeze_time("2026-09-06 05:00:00")
async def test_new_work_time_clears_dismissal(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    await coordinator.async_dismiss_for_today(_fake_call({}))

    # New NFC scan for tomorrow evening is trusted again
    await coordinator.async_set_work_time(_fake_call({"time": "09:00"}))
    assert dt_util.now().date() not in coordinator._dismissed_days or (
        coordinator._work_time_day != dt_util.now().date()
    )
    # today's dismissal still holds, but tomorrow's alarm is scheduled
    assert coordinator._alarm_target is not None


# ---------------------------------------------------------------------------
# tests: mode select
# ---------------------------------------------------------------------------


@freeze_time("2026-09-06 05:00:00")
async def test_mode_vacation_override_and_back(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    assert coordinator.current_mode == MODE_STANDARD

    await coordinator.async_set_mode(MODE_VACATION)
    assert coordinator.current_mode == MODE_VACATION
    assert coordinator._state == STATE_VACATION
    assert coordinator._alarm_target is None

    await coordinator.async_set_mode(MODE_STANDARD)
    assert coordinator.current_mode == MODE_STANDARD
    assert coordinator._state == STATE_SCHEDULED
    assert coordinator._alarm_target is not None


@freeze_time("2026-09-06 05:00:00")
async def test_mode_dismissed(hass: HomeAssistant, coordinator: DacCoordinator):
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    await coordinator.async_set_mode(MODE_DISMISSED)

    assert coordinator.current_mode == MODE_DISMISSED
    assert coordinator._alarm_target is None


# ---------------------------------------------------------------------------
# tests: vacation check via calendar service
# ---------------------------------------------------------------------------


@freeze_time("2026-09-06 07:00:00")
async def test_vacation_check_suppresses_alarm(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """calendar.get_events returning a 'Urlaub' event disables the alarm."""
    events_response = {
        "calendar.vac": {
            "events": [
                {
                    "summary": "Urlaub",
                    "start": {"date": "2026-09-06"},
                    "end": {"date": "2026-09-07"},
                }
            ]
        }
    }

    registry_cls = type(hass.services)

    async def fake_call(self, domain, service, service_data=None, **kwargs):
        class _R:
            def values(self):
                return events_response.values()

        return _R()

    with patch.object(
        registry_cls, "async_call", autospec=True, side_effect=fake_call
    ):
        await coordinator._async_vacation_check()

    assert coordinator._is_vacation is True
    assert coordinator._state == STATE_VACATION
    assert coordinator._alarm_target is None


# ---------------------------------------------------------------------------
# tests: reminder
# ---------------------------------------------------------------------------


@freeze_time("2026-09-06 18:30:00")
async def test_reminder_sent_when_no_work_time(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
):
    """At 20:30 with nothing set for tomorrow -> reminder via notify.test."""
    await coordinator._async_reminder_check(dt_util.now())

    notify_calls = [c for c in recorded if c[0] == "notify"]
    assert len(notify_calls) == 1
    _, service, data = notify_calls[0]
    assert service == "test"
    assert "Standard-Wecker" in data["message"] or "DAC" in data["message"]


@freeze_time("2026-09-06 18:30:00")
async def test_reminder_not_sent_when_work_time_set(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
):
    """A work time for tomorrow suppresses the reminder."""
    await coordinator.async_set_work_time(_fake_call({"time": "08:00"}))
    assert coordinator._work_time_day == dt_util.now().date() + timedelta(days=1)

    await coordinator._async_reminder_check(dt_util.now())
    assert not [c for c in recorded if c[0] == "notify"]


@freeze_time("2026-09-06 18:30:00")
async def test_reminder_skipped_on_vacation(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
):
    coordinator._is_vacation = True
    await coordinator._async_reminder_check(dt_util.now())
    assert not [c for c in recorded if c[0] == "notify"]


@freeze_time("2026-09-06 19:00:00")  # Berlin 21:00, after cutoff -> work day tomorrow
async def test_early_shift_wraps_before_work_day(
    hass: HomeAssistant, coordinator: DacCoordinator
):
    """Work start 00:30 + 60 min offset -> alarm the night *before* (23:30)."""
    await coordinator.async_set_work_time(_fake_call({"time": "00:30"}))

    target_local = dt_util.as_local(coordinator._alarm_target)
    assert target_local.strftime("%H:%M") == "23:30"
    # 2026-09-06 23:30 (the night before the 00:30 shift on 2026-09-07).
    assert target_local.date().isoformat() == "2026-09-06"
    assert coordinator._alarm_day == target_local.date()


@freeze_time("2026-09-06 18:30:00")  # Berlin 20:30 = cutoff
async def test_cutoff_commits_fallback_alarm(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
):
    """At the cutoff the fallback alarm is armed so nobody oversleeps.

    Simulates a restart inside the "awaiting input" window: nothing is
    scheduled, then the cutoff reminder job must commit the default alarm.
    """
    coordinator._set_state(STATE_IDLE)
    coordinator._alarm_target = None
    coordinator._alarm_day = None
    coordinator._alarm_time = None

    await coordinator._async_reminder_check(dt_util.now())

    assert coordinator._state == STATE_SCHEDULED
    assert coordinator._alarm_time.strftime("%H:%M") == "06:00"
    assert coordinator._alarm_day == dt_util.now().date() + timedelta(days=1)
    assert coordinator._alarm_target is not None
    assert [c for c in recorded if c[0] == "notify"]  # reminder still sent


# ---------------------------------------------------------------------------
# tests: persistence
# ---------------------------------------------------------------------------


@freeze_time("2026-09-06 05:00:00")
async def test_state_roundtrip_via_store(
    hass: HomeAssistant, coordinator: DacCoordinator, store, config_entry
):
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    saved = await store.async_load()
    assert saved["work_time"].startswith("15:00")

    # A fresh coordinator restores the work time
    restored = DacCoordinator(hass, config_entry, store=store)
    try:
        await restored.async_restore_state(await store.async_load())
        assert restored._work_time is not None
        assert restored._work_time.strftime("%H:%M") == "15:00"
        assert restored._work_time_day == dt_util.now().date()
        assert restored._alarm_target is not None
    finally:
        restored.async_shutdown()


@freeze_time("2026-09-06 05:00:00")
async def test_restore_skips_stale_work_time(
    hass: HomeAssistant, coordinator: DacCoordinator, store, config_entry
):
    """A stored work time from yesterday is dropped on restore."""
    await coordinator.async_set_work_time(_fake_call({"time": "15:00"}))
    saved = await store.async_load()
    yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
    saved["work_time_day"] = yesterday

    restored = DacCoordinator(hass, config_entry, store=store)
    try:
        await restored.async_restore_state(saved)
        assert restored._work_time is None
    finally:
        restored.async_shutdown()


@freeze_time("2026-09-06 06:00:00")  # Berlin 08:00, alarm fired 20 min ago
async def test_restart_during_alarm_window_resumes(
    hass: HomeAssistant, config_entry, store, recorded
) -> None:
    """A restart right after the alarm fired must resume, not roll to tomorrow.

    The ringing state is not persisted, so the saved state still reads
    "scheduled" – the recent past target has to trigger the resume anyway.
    """
    now = dt_util.now()
    saved = {
        "work_time": "08:00:00",
        "work_time_day": now.date().isoformat(),
        "state": "scheduled",
        "alarm_day": now.date().isoformat(),
        "alarm_target": (now - timedelta(minutes=20)).isoformat(),
        "dismissed": [],
        "stopped": [],
    }
    restored = DacCoordinator(hass, config_entry, store=store)
    try:
        await restored.async_restore_state(saved)
        assert restored._state == STATE_RINGING
        assert any(d == "light" and s == "turn_on" for d, s, _ in recorded)
    finally:
        restored.async_shutdown()


@freeze_time("2026-09-06 06:00:00")
async def test_restore_ignores_long_past_alarm(
    hass: HomeAssistant, config_entry, store, recorded
) -> None:
    """An alarm that fired hours ago is not resumed (window is one hour)."""
    now = dt_util.now()
    saved = {
        "work_time": "08:00:00",
        "work_time_day": now.date().isoformat(),
        "state": "scheduled",
        "alarm_day": now.date().isoformat(),
        "alarm_target": (now - timedelta(hours=3)).isoformat(),
        "dismissed": [],
        "stopped": [],
    }
    restored = DacCoordinator(hass, config_entry, store=store)
    try:
        await restored.async_restore_state(saved)
        assert restored._state != STATE_RINGING
        assert not any(d == "light" for d, _, _ in recorded)
    finally:
        restored.async_shutdown()
