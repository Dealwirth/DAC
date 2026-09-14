"""Tests for the pure Alexa text logic and the AlexaBridge."""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

from freezegun import freeze_time
import pytest

from homeassistant.core import HomeAssistant

from custom_components.dac.alexa import AlexaBridge
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
    real_call = registry_cls.async_call

    async def spy(self, domain, service, service_data=None, **kwargs):
        calls.append((domain, service, dict(service_data or {})))
        return None

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
    assert "stelle einen Wecker auf 05:58 Uhr morgens" in texts
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


async def test_pre_alarm_requires_gate(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """The 2-minute pre-alarm only fires while wecker_aktiv is on."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    _set_state(hass, "input_boolean.wecker_aktiv", "on")
    coordinator._alarm_time = time(6, 0)

    await coordinator.alexa.async_pre_alarm()
    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert len(texts) == 1
    assert texts[0].startswith("stelle einen Wecker auf ")
    assert texts[0].endswith("Uhr morgens") or texts[0].endswith("Uhr abends")

    # Gate off -> no device alarm.
    _set_state(hass, "input_boolean.wecker_aktiv", "off")
    await coordinator.alexa.async_pre_alarm()
    assert len([1 for d, s, _ in service_calls if s == "play_media"]) == 1


def test_pre_alarm_time_text_parses(coordinator) -> None:
    """The pre-alarm time text is always a valid HH:MM time."""
    coordinator._alarm_time = time(6, 0)
    parse_time_str(coordinator.alexa.pre_alarm_time_text())
