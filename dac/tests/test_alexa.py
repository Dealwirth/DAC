"""Tests for the DAC app Alexa bridge (Echo device alarm)."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.alexa import AlexaBridge
from app.config import settings


class FakeCoordinator:
    """Minimal coordinator stand-in with a controllable desired alarm."""

    def __init__(self) -> None:
        self.desired = None
        self._alarm_time = None
        self._alarm_target = None
        self._alarm_day = None
        self._is_vacation = False
        self._state = "scheduled"
        self._dismissed_days: set = set()
        self.pre_alarm = 2

    def desired_alarm_text(self):
        return self.desired

    def schedule_volume_restore(self, player, volume):  # pragma: no cover
        pass


def _bridge(monkeypatch, player="media_player.echo") -> AlexaBridge:
    settings.update({"alexa_enabled": True, "alexa_media_player": player})
    return AlexaBridge(FakeCoordinator())


async def test_disabled_without_player(monkeypatch, fake_ha) -> None:
    settings.update({"alexa_enabled": True, "alexa_media_player": ""})
    bridge = AlexaBridge(FakeCoordinator())
    assert bridge.enabled is False
    await bridge.async_sync()
    assert fake_ha.calls == []


async def test_sync_places_alarm_and_writes_helper(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "")

    await bridge.async_sync()

    media = fake_ha.calls_for("media_player", "play_media")
    assert any("stelle einen Wecker auf 05:43" in c["media_content_id"] for c in media)
    assert fake_ha.states["input_text.gestellter_alexa_wecker"]["state"] == "05:43"


async def test_sync_noop_when_helper_matches(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    await bridge.async_sync()
    assert fake_ha.calls_for("media_player", "play_media") == []


async def test_sync_changes_time_clears_then_places(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "06:00")
    await bridge.async_sync()
    texts = [c["media_content_id"] for c in fake_ha.calls_for("media_player", "play_media")]
    assert texts[0].startswith("lösche den Wecker um 06:00")
    assert any(t.startswith("stelle einen Wecker auf 05:43") for t in texts)


async def test_force_sync_does_not_clear_same_time(monkeypatch, fake_ha) -> None:
    """Regression: force-sync must re-place, never delete (live bug)."""
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    await bridge.async_sync(force=True)
    texts = [c["media_content_id"] for c in fake_ha.calls_for("media_player", "play_media")]
    assert any(t.startswith("stelle einen Wecker auf 05:43") for t in texts)
    assert not any(t.startswith("lösche den Wecker") for t in texts)


async def test_watchdog_replaces_lost_alarm(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    tomorrow = (datetime.now().astimezone() + timedelta(days=1)).replace(
        hour=6, minute=0, second=0, microsecond=0
    ).isoformat()
    fake_ha.set_state(
        "sensor.echo_next_alarm", "unknown",
        {"sorted_all": [{"status": "OFF", "date_time": tomorrow}]},
    )
    await bridge.async_ensure_scheduled()
    texts = [c["media_content_id"] for c in fake_ha.calls_for("media_player", "play_media")]
    assert any(t.startswith("stelle einen Wecker auf 05:43") for t in texts)


async def test_watchdog_keeps_existing_alarm(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "05:43")
    tomorrow = (datetime.now().astimezone() + timedelta(days=1)).replace(
        hour=5, minute=43, second=0, microsecond=0
    ).isoformat()
    fake_ha.set_state(
        "sensor.echo_next_alarm", "unknown",
        {"sorted_all": [{"status": "ON", "date_time": tomorrow}]},
    )
    await bridge.async_ensure_scheduled()
    assert fake_ha.calls_for("media_player", "play_media") == []


async def test_orphan_alarm_is_removed(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = None
    bridge.restore_last_placed("06:13")
    tomorrow = (datetime.now().astimezone() + timedelta(days=1)).replace(
        hour=6, minute=13, second=0, microsecond=0
    ).isoformat()
    fake_ha.set_state(
        "sensor.echo_next_alarm", "unknown",
        {"sorted_all": [{"status": "ON", "date_time": tomorrow}]},
    )
    await bridge.async_ensure_scheduled()
    texts = [c["media_content_id"] for c in fake_ha.calls_for("media_player", "play_media")]
    assert any(t.startswith("lösche den Wecker um 06:13") for t in texts)


async def test_orphan_cleanup_never_touches_foreign_alarms(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = None
    tomorrow = (datetime.now().astimezone() + timedelta(days=1)).replace(
        hour=7, minute=0, second=0, microsecond=0
    ).isoformat()
    fake_ha.set_state(
        "sensor.echo_next_alarm", "unknown",
        {"sorted_all": [{"status": "ON", "date_time": tomorrow}]},
    )
    await bridge.async_ensure_scheduled()
    assert fake_ha.calls_for("media_player", "play_media") == []


async def test_pre_alarm_is_placed_once_per_minute(monkeypatch, fake_ha) -> None:
    bridge = _bridge(monkeypatch)
    await bridge.async_pre_alarm()
    await bridge.async_pre_alarm()
    assert len(fake_ha.calls_for("media_player", "play_media")) == 1


async def test_named_alarm_uses_stop_word(monkeypatch, fake_ha) -> None:
    settings.update({"alexa_alarm_name": "Wecker aus"})
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "")
    await bridge.async_sync()
    texts = [c["media_content_id"] for c in fake_ha.calls_for("media_player", "play_media")]
    assert any("namens Wecker aus" in t for t in texts)


async def test_alexa_failure_is_swallowed(monkeypatch, fake_ha) -> None:
    """A broken Echo must never crash the alarm logic."""
    bridge = _bridge(monkeypatch)
    bridge.coordinator.desired = "05:43"
    fake_ha.fail_domains.add("media_player")
    fake_ha.set_state("input_text.gestellter_alexa_wecker", "")
    await bridge.async_sync()  # must not raise
