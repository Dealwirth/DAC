"""Tests for the pure Alexa text logic and the AlexaBridge."""
from __future__ import annotations

from datetime import time
from unittest.mock import patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.dac.const import (
    ALEXA_CLEAR_TEXT,
    ALEXA_SET_TEXT,
    CONF_ALEXA_ENABLED,
)
from custom_components.dac.coordinator import DacCoordinator
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
    """Sync places the alarm for the computed wake time and stores it in the helper.

    The wake time is the work start MINUS the offset (06:00 default - 60 min =
    05:00), minus the 2-minute pre-alarm -> 04:58.
    """
    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._reschedule_alarm()
    await coordinator.alexa.async_sync()

    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert any(t.startswith("stelle einen Wecker auf 04:58 Uhr morgens") for t in texts)
    helper_writes = [data.get("value") for d, s, data in service_calls if s == "set_value"]
    assert "04:58" in helper_writes


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


async def test_stop_clears_pending_pre_alarm(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """A stop must also delete the short pre-alarm the loop placed.

    The pre-alarm is what actually wakes the user. It is not tracked in the
    input_text helper, so without an explicit delete the Echo would still ring
    a few minutes after "Wecker stoppen".
    """
    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._alarm_time = time(6, 0)
    await coordinator.alexa.async_pre_alarm()

    await coordinator.alexa.async_on_stop()

    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert any(t.startswith("lösche den Wecker um ") for t in texts)


async def test_clear_pre_alarm_without_one_sends_nothing(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Without a pending pre-alarm no delete command is sent."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    await coordinator.alexa.async_clear_pre_alarm()
    assert not [1 for d, s, _ in service_calls if s == "play_media"]


async def test_pre_alarm_repeats_when_minute_changes(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """The loop re-places the pre-alarm once the target minute moved on."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._alarm_time = time(6, 0)
    await coordinator.alexa.async_pre_alarm()
    first = len([1 for d, s, _ in service_calls if s == "play_media"])
    await coordinator.alexa.async_pre_alarm()  # same minute -> suppressed
    assert len([1 for d, s, _ in service_calls if s == "play_media"]) == first


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
    """A configured alarm name is passed to Alexa so a routine can stop DAC."""
    from custom_components.dac.const import CONF_ALEXA_ALARM_NAME

    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._options[CONF_ALEXA_ALARM_NAME] = "Wecker aus"
    coordinator._alarm_time = time(6, 0)

    await coordinator.alexa.async_pre_alarm()
    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert texts and "namens Wecker aus" in texts[0]


async def test_alarm_is_plain_without_name(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Without a configured name the alarm is placed plain.

    A name makes Alexa ask back or refuse the command on some devices, which is
    why it is opt-in; the plain command must contain no 'namens'.
    """
    from custom_components.dac.const import CONF_ALEXA_ALARM_NAME

    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._options[CONF_ALEXA_ALARM_NAME] = ""
    coordinator._alarm_time = time(6, 0)

    await coordinator.alexa.async_pre_alarm()
    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert texts
    assert "namens" not in texts[0]
    assert texts[0].startswith("stelle einen Wecker auf ")


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


@freeze_time("2026-09-06 18:00:00")  # Berlin 20:00
async def test_bridge_sync_places_alarm_for_tomorrow(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """A work time set in the evening targets tomorrow -> the Echo alarm MUST be placed.

    Regression for a live bug: ``async_sync`` only placed the device alarm when
    the computed alarm day was *today*. A work time set in the evening (the
    normal case) targets tomorrow, so the Echo alarm was never created at all –
    the user woke up with no alarm.
    """
    from tests.conftest import FakeCall

    coordinator._options[CONF_ALEXA_ENABLED] = True
    await coordinator.async_set_work_time(FakeCall({"time": "06:45"}))
    assert coordinator._alarm_day is not None
    assert coordinator._alarm_day > __import__("homeassistant.util.dt", fromlist=["dt"]).now().date()

    await coordinator.alexa.async_sync()

    texts = [data.get("media_content_id", "") for d, s, data in service_calls if s == "play_media"]
    assert any(t.startswith("stelle einen Wecker auf ") for t in texts), texts


# --------------------------------------------------------------- speak/reminder
@freeze_time("2026-09-06 19:00:00")
async def test_speak_uses_alexa_media_notify_and_restores_volume(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """The spoken reminder goes to the device notify service and restores volume.

    The Echo is turned down for the reminder and back up afterwards, so a 21:00
    reminder never blasts the room.
    """
    from custom_components.dac.const import CONF_REMINDER_ALEXA_VOLUME

    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._options[CONF_REMINDER_ALEXA_VOLUME] = 15
    hass.states.async_set(
        "media_player.echo", "idle", {"volume_level": 0.4, "friendly_name": "Echo"}
    )
    hass.services.async_register("notify", "alexa_media_echo", lambda call: None)

    spoke = await coordinator.alexa.async_speak("Bitte den Wecker stellen.")

    assert spoke is True
    volumes = [d.get("volume_level") for dom, s, d in service_calls if s == "volume_set"]
    assert 0.15 in volumes
    assert any(dom == "notify" and s == "alexa_media_echo" for dom, s, _ in service_calls)


async def test_speak_returns_false_without_service(
    hass: HomeAssistant, coordinator, service_calls: list[tuple[str, str, dict]]
) -> None:
    """Without a matching notify service the reminder is skipped silently."""
    coordinator._options[CONF_ALEXA_ENABLED] = True
    assert await coordinator.alexa.async_speak("Test") is False
    assert not [1 for dom, s, _ in service_calls if dom == "notify"]


@freeze_time("2026-09-06 19:30:00")
async def test_reminder_speaks_on_echo_when_enabled(
    hass: HomeAssistant, coordinator: DacCoordinator, recorded
) -> None:
    """The 21:00 reminder is also spoken on the Echo when the option is on."""
    from custom_components.dac.const import CONF_REMINDER_VIA_ALEXA

    coordinator._options[CONF_ALEXA_ENABLED] = True
    coordinator._options[CONF_REMINDER_VIA_ALEXA] = True
    hass.states.async_set("media_player.echo", "idle", {"volume_level": 0.5})
    hass.services.async_register("notify", "alexa_media_echo", lambda call: None)

    await coordinator._async_reminder_check(dt_util.now())

    notify_calls = [c for c in recorded if c[0] == "notify"]
    assert any("alexa_media_echo" == c[1] for c in notify_calls)
