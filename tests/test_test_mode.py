"""Tests for the DAC test mode, the configurable wake loop and the Alexa stop word."""
from __future__ import annotations

from datetime import time, timedelta

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.dac.const import (
    CONF_ALEXA_ENABLED,
    CONF_LOOP_INTERVAL_MINUTES,
    CONF_STOP_WORD,
    CONF_TEST_MODE_MINUTES,
    DEFAULT_LOOP_INTERVAL_MINUTES,
    DEFAULT_STOP_WORD,
)
from custom_components.dac.coordinator import DacCoordinator
from tests.conftest import FakeCall


def _record_calls(hass: HomeAssistant):
    """Context manager capturing light/media_player service calls."""
    from unittest.mock import patch

    calls: list[tuple[str, str, dict]] = []
    registry_cls = type(hass.services)
    real_call = registry_cls.async_call

    async def spy(self, domain, service, service_data=None, **kwargs):
        if domain in ("light", "media_player"):
            calls.append((domain, service, dict(service_data or {})))
            return None
        return await real_call(self, domain, service, service_data, **kwargs)

    patcher = patch.object(registry_cls, "async_call", autospec=True, side_effect=spy)
    return patcher, calls


# --------------------------------------------------------------- loop interval
async def test_loop_interval_default_and_bounds(coordinator) -> None:
    """The wake loop interval defaults to 5 and is clamped to 1..60."""
    assert coordinator.loop_interval_minutes == DEFAULT_LOOP_INTERVAL_MINUTES
    coordinator._options[CONF_LOOP_INTERVAL_MINUTES] = 2
    assert coordinator.loop_interval_minutes == 2
    coordinator._options[CONF_LOOP_INTERVAL_MINUTES] = 0
    assert coordinator.loop_interval_minutes == 1
    coordinator._options[CONF_LOOP_INTERVAL_MINUTES] = 999
    assert coordinator.loop_interval_minutes == 60


@freeze_time("2026-09-06 11:59:59")  # Berlin 13:59:59
async def test_loop_repeats_with_configured_interval(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """A 1-minute interval makes the alarm repeat once per minute."""
    coordinator._options[CONF_LOOP_INTERVAL_MINUTES] = 1
    coordinator._work_time = time(13, 0)
    coordinator._work_time_day = dt_util.now().date()
    coordinator._reschedule_alarm()
    assert coordinator._alarm_target is not None

    patcher, calls = _record_calls(hass)
    with patcher:
        await coordinator._alarm_fired(dt_util.now())
        await hass.async_block_till_done()
        first = len([c for c in calls if c[0] == "light" and c[1] == "turn_on"])

        # One interval later the loop must fire again.
        await coordinator._loop_tick(dt_util.now() + timedelta(minutes=1))
        await hass.async_block_till_done()
        second = len([c for c in calls if c[0] == "light" and c[1] == "turn_on"])
    assert second > first


# ------------------------------------------------------------------- test mode
@freeze_time("2026-09-06 10:00:00")
async def test_test_alarm_arms_and_rings(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """start_test_alarm arms an alarm N minutes ahead and rings through the loop."""
    patcher, calls = _record_calls(hass)
    with patcher:
        await coordinator.async_start_test_alarm(FakeCall({"minutes": 1}))
        assert coordinator.test_mode_active is True
        assert coordinator._test_target is not None
        assert coordinator._state == "scheduled"

        # Ring it (simulates the point-in-time trigger firing).
        await coordinator._alarm_fired(coordinator._test_target)
        await hass.async_block_till_done()
    assert coordinator._state == "ringing"
    assert any(c[0] == "light" and c[1] == "turn_on" for c in calls)


@freeze_time("2026-09-06 10:00:00")
async def test_test_alarm_uses_configured_minutes(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """Without an explicit override the configured test duration is used."""
    coordinator._options[CONF_TEST_MODE_MINUTES] = 3
    await coordinator.async_start_test_alarm(FakeCall({}))
    delta = coordinator._test_target - dt_util.now()
    assert timedelta(minutes=3) - timedelta(seconds=1) <= delta <= timedelta(minutes=3)


@freeze_time("2026-09-06 10:00:00")
async def test_test_alarm_can_be_cancelled(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """cancel_test_alarm clears the pending test and restores the real schedule."""
    # A real work time must survive the test round-trip.
    await coordinator.async_set_work_time(FakeCall({"time": "15:00"}))
    real_target = coordinator._alarm_target
    await coordinator.async_start_test_alarm(FakeCall({"minutes": 5}))
    assert coordinator.test_mode_active is True
    assert coordinator._alarm_target == real_target  # real alarm untouched

    await coordinator.async_cancel_test_alarm(FakeCall({}))
    assert coordinator.test_mode_active is False
    # The real alarm is scheduled again and was never lost.
    assert coordinator._alarm_target == real_target


@freeze_time("2026-09-06 10:00:00")
async def test_test_alarm_stops_like_real_alarm(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """Stopping the ringing test alarm ends the loop and clears the test flag."""
    await coordinator.async_set_work_time(FakeCall({"time": "15:00"}))
    await coordinator.async_start_test_alarm(FakeCall({"minutes": 1}))
    await coordinator._alarm_fired(coordinator._test_target)
    assert coordinator._state == "ringing"

    await coordinator.async_stop_alarm(FakeCall({}))
    assert coordinator._state == "stopped"
    assert coordinator.test_mode_active is False
    assert coordinator._loop_unsub is None


@freeze_time("2026-09-06 10:00:00")
async def test_stopped_test_alarm_keeps_real_alarm(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """Stopping the test alarm must not consume today's real work time."""
    await coordinator.async_set_work_time(FakeCall({"time": "15:00"}))
    real_target = coordinator._alarm_target
    assert real_target is not None

    await coordinator.async_start_test_alarm(FakeCall({"minutes": 1}))
    await coordinator._alarm_fired(coordinator._test_target)
    await coordinator.async_stop_alarm(FakeCall({}))
    await hass.async_block_till_done()

    # The real alarm is still armed for the same time (not rolled to tomorrow).
    assert coordinator._alarm_target == real_target


@freeze_time("2026-09-06 10:00:00")
async def test_test_alarm_survives_reschedule(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """An option change must not steal the test alarm slot."""
    await coordinator.async_start_test_alarm(FakeCall({"minutes": 2}))
    target = coordinator._test_target
    coordinator.async_set_options(dict(coordinator.options))
    assert coordinator._test_target == target
    assert coordinator.test_mode_active is True


# ------------------------------------------------------------------ stop word
def test_stop_word_default_and_override(coordinator) -> None:
    assert coordinator.alexa.stop_word == DEFAULT_STOP_WORD
    coordinator._options[CONF_STOP_WORD] = "Aufwachen"
    assert coordinator.alexa.stop_word == "Aufwachen"
    coordinator._options[CONF_STOP_WORD] = "   "
    assert coordinator.alexa.stop_word == DEFAULT_STOP_WORD


async def test_alexa_alarm_is_labelled_with_stop_word(
    hass: HomeAssistant, coordinator: DacCoordinator
) -> None:
    """Every alarm DAC places carries the stop word as its Alexa label."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._options[CONF_STOP_WORD] = "Wecker aus"
    calls: list[tuple[str, str, dict]] = []
    from unittest.mock import patch

    registry_cls = type(hass.services)

    async def spy(self, domain, service, service_data=None, **kwargs):
        calls.append((domain, service, dict(service_data or {})))

    with patch.object(registry_cls, "async_call", autospec=True, side_effect=spy):
        await coordinator.alexa.async_set_alarm(FakeCall({"time": "07:15"}))

    texts = [data.get("media_content_id", "") for d, s, data in calls if s == "play_media"]
    assert any(t.endswith("namens Wecker aus") for t in texts)


@pytest.mark.parametrize("minutes", [None, 1, 15])
def test_start_test_schema_accepts_minutes(minutes) -> None:
    """The service schema accepts an optional minutes field."""
    from custom_components.dac import START_TEST_SCHEMA

    payload = {} if minutes is None else {"minutes": minutes}
    validated = START_TEST_SCHEMA(payload)
    assert validated.get("minutes") == minutes
