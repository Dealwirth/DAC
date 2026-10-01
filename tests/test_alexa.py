"""Tests for the pure Alexa text logic and the AlexaBridge."""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant

from custom_components.dac.const import (
    ALEXA_CLEAR_TEXT,
    ALEXA_SET_TEXT,
    CONF_ALEXA_ENABLED,
)
from custom_components.dac.logic import (
    alexa_clear_text,
    alexa_set_text,
    format_alexa_time,
    parse_time_str,
    split_am_pm,
)


# --------------------------------------------------------------------- text
def test_split_am_pm() -> None:
    """Hour < 12 -> morgens, else abends (24h system)."""
    assert split_am_pm(time(0, 0)) == "morgens"
    assert split_am_pm(time(5, 0)) == "morgens"
    assert split_am_pm(time(11, 59)) == "morgens"
    assert split_am_pm(time(12, 0)) == "abends"
    assert split_am_pm(time(17, 0)) == "abends"
    assert split_am_pm(time(23, 45)) == "abends"


def test_alexa_set_text_morgens() -> None:
    """'stelle einen Wecker auf 05:00 Uhr morgens' – no follow-up questions."""
    assert alexa_set_text(time(5, 0)) == "stelle einen Wecker auf 05:00 Uhr morgens"


def test_alexa_set_text_abends() -> None:
    assert alexa_set_text(time(17, 0)) == "stelle einen Wecker auf 17:00 Uhr abends"


def test_alexa_clear_text() -> None:
    """Exact deletion: 'lösche den Wecker um 06:00 Uhr'."""
    assert alexa_clear_text(time(6, 0)) == "lösche den Wecker um 06:00 Uhr"


def test_format_alexa_time_drops_seconds() -> None:
    assert format_alexa_time(time(6, 5, 30)) == "06:05"


def test_templates_consistent() -> None:
    assert ALEXA_SET_TEXT.format(time="05:00", tod="morgens") == alexa_set_text(time(5, 0))
    assert ALEXA_CLEAR_TEXT.format(time="06:00") == alexa_clear_text(time(6, 0))


# ------------------------------------------------------------------- bridge
@pytest.fixture
def service_calls(hass: HomeAssistant) -> list[tuple[str, str, dict]]:
    """Capture all service calls DAC makes during a test."""
    calls: list[tuple[str, str, dict]] = []
    registry_cls = type(hass.services)

    async def spy(self, domain, service, service_data=None, **kwargs):
        calls.append((domain, service, dict(service_data or {})))

    with patch.object(registry_cls, "async_call", autospec=True, side_effect=spy):
        yield calls


def _set_state(hass: HomeAssistant, entity_id: str, value: str) -> None:
    hass.states.async_set(entity_id, value, {})


def test_bridge_disabled_by_default(hass: HomeAssistant, coordinator) -> None:
    """Without CONF_ALEXA_ENABLED the bridge is a no-op."""
    assert coordinator.alexa.enabled is False


async def test_bridge_stored_alarm_reads_helper(hass: HomeAssistant, coordinator) -> None:
    """The helper value is parsed and normalized to HH:MM."""
    _set_state(hass, "input_text.gestellter_alexa_wecker", "06:00")
    assert coordinator.alexa.stored_alarm() == "06:00"
    _set_state(hass, "input_text.gestellter_alexa_wecker", "unavailable")
    assert coordinator.alexa.stored_alarm() is None
    _set_state(hass, "input_text.gestellter_alexa_wecker", "keine zeit")
    assert coordinator.alexa.stored_alarm() is None


@freeze_time("2026-09-06 02:00:00")  # Berlin 04:00 -> default alarm today 06:00
async def test_bridge_sync_places_only_own_alarm(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Sync places today's alarm (with pre-alarm shift) and stores it in the helper."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._reschedule_alarm()
    await coordinator.alexa.async_sync()

    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert any(t.startswith("stelle einen Wecker auf 05:58 Uhr morgens") for t in texts)
    helper_writes = [data.get("value") for d, s, data in service_calls if s == "set_value"]
    assert "05:58" in helper_writes


async def test_bridge_sync_disabled_writes_nothing(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Bridge off: nothing is sent, helper stays untouched."""
    await coordinator.alexa.async_sync()
    assert service_calls == []


async def test_clear_own_only_deletes_stored(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """clear_own deletes exactly the stored alarm (Tag 2/4 semantics)."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    _set_state(hass, "input_text.gestellter_alexa_wecker", "06:00")

    await coordinator.alexa.async_clear_own()

    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert "lösche den Wecker um 06:00 Uhr" in texts
    assert any(s == "set_value" and data.get("value") == "" for d, s, data in service_calls)


async def test_clear_own_without_stored_sends_nothing(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """No stored alarm -> no Alexa command at all (protects manual alarms)."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    _set_state(hass, "input_text.gestellter_alexa_wecker", "")

    await coordinator.alexa.async_clear_own()

    assert not [1 for d, s, _ in service_calls if s == "play_media"]


async def test_on_stop_turns_off_gate(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Tag 4: stop kills own alarm and turns off the wecker_aktiv helper."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    _set_state(hass, "input_text.gestellter_alexa_wecker", "06:00")
    _set_state(hass, "input_boolean.wecker_aktiv", "on")

    await coordinator.alexa.async_on_stop()

    assert any(s == "turn_off" and d == "input_boolean" for d, s, _ in service_calls)
    assert any(s == "set_value" and data.get("value") == "" for d, s, data in service_calls)
    assert any(
        s == "play_media" and "lösche den Wecker um 06:00 Uhr" in data.get("media_content_id", "")
        for d, s, data in service_calls
    )


async def test_pre_alarm_ignores_gate(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """The pre-alarm fires while ringing even if the gate is off.

    DAC turns the gate on itself when the alarm fires, so the pre-alarm must
    not depend on it – otherwise a failed gate write could silence the Echo.
    """
    coordinator._options[CONF_ALEXA_ENABLED] = True
    _set_state(hass, "input_boolean.wecker_aktiv", "off")
    coordinator._alarm_time = time(6, 0)

    await coordinator.alexa.async_pre_alarm()
    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert len(texts) == 1
    assert texts[0].startswith("stelle einen Wecker auf ")
    assert "Uhr morgens" in texts[0] or "Uhr abends" in texts[0]


async def test_command_is_always_custom_text(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """DAC only ever sends a plain text command – no TTS/announcements."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    await coordinator.alexa.async_send_text("test")
    assert service_calls[-1][2]["media_content_type"] == "custom"
    assert service_calls[-1][2]["media_content_id"] == "test"


async def test_alarm_name_carries_stop_word(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """The Echo alarm is named with the stop word so an Alexa routine can stop DAC."""
    from custom_components.dac.const import CONF_STOP_WORD

    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._options[CONF_STOP_WORD] = "Wecker aus"
    coordinator._alarm_time = time(6, 0)

    await coordinator.alexa.async_pre_alarm()
    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert texts and "namens Wecker aus" in texts[0]


async def test_set_gate_turns_helper_on_and_off(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """async_set_gate mirrors the wecker_aktiv helper (Tag 1 / Tag 4)."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    await coordinator.alexa.async_set_gate(True)
    assert ("input_boolean", "turn_on") in [(d, s) for d, s, _ in service_calls]
    await coordinator.alexa.async_set_gate(False)
    assert ("input_boolean", "turn_off") in [(d, s) for d, s, _ in service_calls]


def test_pre_alarm_time_text_parses(coordinator) -> None:
    """The pre-alarm time text is always a valid HH:MM time."""
    coordinator._alarm_time = time(6, 0)
    parse_time_str(coordinator.alexa.pre_alarm_time_text())


async def test_service_set_alarm_uses_explicit_time(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """set_alexa_alarm with an explicit time replaces DAC's own alarm."""
    from tests.conftest import FakeCall

    coordinator._options[CONF_ALEXA_ENABLED] = True
    _set_state(hass, "input_text.gestellter_alexa_wecker", "06:00")

    await coordinator.alexa.async_set_alarm(FakeCall({"time": "07:15"}))

    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert "lösche den Wecker um 06:00 Uhr" in texts
    assert any(t.startswith("stelle einen Wecker auf 07:15 Uhr morgens") for t in texts)
    helper_writes = [data.get("value") for d, s, data in service_calls if s == "set_value"]
    assert "07:15" in helper_writes


async def test_service_set_alarm_without_time_syncs(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Without a time the service falls back to the computed sync."""
    from homeassistant.util import dt as dt_util

    from tests.conftest import FakeCall

    coordinator._options[CONF_ALEXA_ENABLED] = True
    # A scheduled alarm for today makes the sync place a device alarm.
    coordinator._alarm_day = dt_util.now().date()
    coordinator._alarm_time = time(6, 0)

    await coordinator.alexa.async_set_alarm(FakeCall({}))

    assert any(s == "set_value" for d, s, _ in service_calls)
