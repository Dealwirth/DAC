"""Device alarm on Amazon Echo (via the alexa_media integration).

Port of the former HACS integration's ``alexa.py``. DAC places a *real* alarm
on the Echo device with a text command (``media_player.play_media``,
``media_content_type: custom``). Only alarms DAC itself placed are ever
deleted – manually configured Echo alarms are left untouched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .config import settings
from .ha_client import HomeAssistantError, ha
from .logic import (
    ALEXA_CLEAR_TEXT,
    ALEXA_SET_NAMED_TEXT,
    ALEXA_SET_TEXT,
    format_alexa_time,
    parse_time_str,
    split_am_pm,
)

log = logging.getLogger("dac.alexa")

DEFAULT_HELPER = "input_text.gestellter_alexa_wecker"
DEFAULT_GATE = "input_boolean.wecker_aktiv"


class AlexaBridge:
    """Place, verify and remove the alarm on the Echo device."""

    def __init__(self, coordinator: Any) -> None:
        """Bind the bridge to the coordinator that owns the schedule."""
        self.coordinator = coordinator
        self._pre_alarm = None
        self._last_pre_alarm_time: str | None = None
        self._sensor_cache: tuple[datetime, dict[str, Any] | None] | None = None
        # The time DAC last placed on the device (persisted by the coordinator)
        # so an orphaned alarm can still be removed after the schedule emptied.
        self._last_placed = None

    # ------------------------------------------------------------ properties
    @property
    def enabled(self) -> bool:
        """True when the Alexa integration is on and a player is configured."""
        if not settings.get_bool("alexa_enabled", True):
            return False
        return bool(self.player)

    @property
    def player(self) -> str | None:
        """The Echo media_player entity."""
        value = settings.get("alexa_media_player")
        return str(value) if value else None

    @property
    def helper(self) -> str:
        return str(settings.get("alexa_text_helper") or DEFAULT_HELPER)

    @property
    def gate_boolean(self) -> str:
        return str(settings.get("alexa_enabled_boolean") or DEFAULT_GATE)

    @property
    def pre_alarm_minutes(self) -> int:
        try:
            return max(0, int(settings.get("pre_alarm_minutes", 2)))
        except (TypeError, ValueError):
            return 2

    @property
    def alarm_name(self) -> str:
        """Optional alarm name (lets an Alexa routine trigger on it)."""
        value = settings.get("alexa_alarm_name")
        return str(value).strip() if value else ""

    @property
    def stop_word(self) -> str:
        """Name given to DAC alarms so an Alexa routine can stop DAC."""
        value = str(settings.get("stop_word") or "Wecker aus").strip()
        return value or "Wecker aus"

    @property
    def last_placed(self) -> str | None:
        """'HH:MM' of the alarm DAC last placed, or None."""
        return format_alexa_time(self._last_placed) if self._last_placed else None

    # ------------------------------------------------------------- device io
    def restore_last_placed(self, value: str | None) -> None:
        """Restore the persisted last-placed time after a restart."""
        if not value:
            self._last_placed = None
            return
        try:
            self._last_placed = parse_time_str(value)
        except ValueError:
            self._last_placed = None

    async def stored_alarm(self) -> str | None:
        """The alarm time DAC has placed on the device ('HH:MM' or None)."""
        value = await ha.state_value(self.helper, "")
        if not value or value in ("unknown", "unavailable", "none"):
            return None
        try:
            return format_alexa_time(parse_time_str(value))
        except ValueError:
            return None

    async def gate_on(self) -> bool:
        """True while the wecker_aktiv gate is on."""
        return await ha.state_value(self.gate_boolean, "off") == "on"

    async def _next_alarm_sensor(self) -> dict[str, Any] | None:
        """The alexa_media next-alarm sensor for the configured player.

        The entity id suffix is localized (``_next_alarm``,
        ``_nachster_alarm``, …), so the sensor is located by its ``sorted_all``
        attribute instead of a hard-coded name. The lookup is cached briefly to
        keep the watchdog cheap.
        """
        object_id = str(self.player or "").split(".", 1)[-1]
        if not object_id:
            return None
        now = datetime.now().astimezone()
        cached = self._sensor_cache
        if cached and now - cached[0] < timedelta(minutes=5):
            return cached[1]
        state = await ha.state(f"sensor.{object_id}_next_alarm")
        if state is None:
            for candidate in (
                f"sensor.{object_id}_nachster_alarm",
                f"sensor.{object_id}_naechster_alarm",
            ):
                state = await ha.state(candidate)
                if state is not None:
                    break
        if state is None or (state.get("attributes") or {}).get("sorted_all") is None:
            state = None
            for item in await ha.states():
                entity_id = str(item.get("entity_id") or "")
                if (
                    entity_id.startswith("sensor.")
                    and object_id in entity_id
                    and (item.get("attributes") or {}).get("sorted_all") is not None
                ):
                    state = item
                    break
        self._sensor_cache = (now, state)
        return state

    async def device_has_alarm(self, time_text: str) -> bool:
        """True when the Echo really has an active alarm at ``time_text``.

        Reads the alexa_media next-alarm sensor. When that sensor is missing
        the method returns True so a forced sync is not triggered on every
        refresh.
        """
        state = await self._next_alarm_sensor()
        if state is None:
            return True
        try:
            want = parse_time_str(time_text).strftime("%H:%M")
        except ValueError:
            return True
        now = datetime.now().astimezone()
        for alarm in (state.get("attributes") or {}).get("sorted_all") or []:
            if alarm.get("status") != "ON":
                continue
            raw = alarm.get("date_time")
            if not raw:
                continue
            try:
                when = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            except ValueError:
                continue
            if when < now - timedelta(minutes=1):
                continue
            if when.strftime("%H:%M") == want:
                return True
        return False

    # ------------------------------------------------------------- commands
    def _set_command(self, value) -> str:
        """The 'set an alarm' command (named only when a name is configured)."""
        time_text = format_alexa_time(value)
        tod = split_am_pm(value)
        if self.alarm_name:
            return ALEXA_SET_NAMED_TEXT.format(time=time_text, tod=tod, label=self.alarm_name)
        return ALEXA_SET_TEXT.format(time=time_text, tod=tod)

    async def async_send_text(self, text: str) -> None:
        """Send a plain Alexa text command to the Echo device."""
        player = self.player
        if not player:
            return
        try:
            await ha.call_service(
                "media_player",
                "play_media",
                {
                    "entity_id": player,
                    "media_content_type": "custom",
                    "media_content_id": text,
                },
            )
        except HomeAssistantError as err:
            log.warning("DAC Alexa command failed (%s): %s", player, err)

    async def async_set_gate(self, on: bool) -> None:
        """Turn the wecker_aktiv input_boolean on/off (safety net)."""
        if not self.enabled:
            return
        try:
            await ha.call_service(
                "input_boolean", "turn_on" if on else "turn_off", {"entity_id": self.gate_boolean}
            )
        except HomeAssistantError as err:
            log.debug("DAC could not set %s: %s", self.gate_boolean, err)

    async def _async_write_helper(self, value: str) -> None:
        """Store the currently placed alarm in the input_text helper."""
        try:
            await ha.call_service(
                "input_text", "set_value", {"entity_id": self.helper, "value": value}
            )
        except HomeAssistantError as err:
            log.warning("DAC could not update helper %s: %s", self.helper, err)

    # --------------------------------------------------------------- sync
    async def async_sync(self, force: bool = False) -> None:
        """Make the device alarm match what DAC wants.

        Clearing only happens when the time really changes; at the same time
        the alarm is merely re-placed. Clearing and placing in quick succession
        made the Echo drop the second command (live bug: "Sync" left no alarm).
        """
        if not self.enabled:
            return
        desired = self.coordinator.desired_alarm_text()
        stored = await self.stored_alarm()
        if stored == desired and not force:
            return
        if stored and stored != desired:
            await self.async_send_text(ALEXA_CLEAR_TEXT.format(time=stored))
        if desired:
            await self.async_send_text(self._set_command(parse_time_str(desired)))
        self._last_placed = parse_time_str(desired) if desired else None
        await self._async_write_helper(desired or "")

    async def async_ensure_scheduled(self) -> None:
        """Re-place the alarm if the Echo lost it (watchdog, every 30 min)."""
        if not self.enabled:
            return
        desired = self.coordinator.desired_alarm_text()
        if not desired:
            await self._async_clear_orphan()
            await self.async_sync()
            return
        if await self.device_has_alarm(desired):
            return
        log.info("DAC: Echo alarm %s is missing on %s – re-placing it", desired, self.player)
        await self.async_sync(force=True)

    async def _async_clear_orphan(self) -> None:
        """Remove a DAC-placed alarm after the schedule emptied."""
        if not self.enabled or self._last_placed is None:
            return
        text = format_alexa_time(self._last_placed)
        self._last_placed = None
        if not await self.device_has_alarm(text):
            return
        log.info("DAC: removing orphaned Echo alarm %s on %s", text, self.player)
        await self.async_send_text(ALEXA_CLEAR_TEXT.format(time=text))
        await self._async_write_helper("")

    async def async_set_alarm(self, value, day: str | None = None) -> None:
        """Place an explicit alarm time on the device."""
        if not self.enabled:
            return
        text = format_alexa_time(value)
        stored = await self.stored_alarm()
        if stored and stored != text:
            await self.async_send_text(ALEXA_CLEAR_TEXT.format(time=stored))
        await self.async_send_text(self._set_command(value))
        self._last_placed = value
        await self._async_write_helper(text)
        log.debug("DAC placed a manual Alexa alarm for %s (%s)", text, day)

    async def async_clear_own(self) -> None:
        """Delete only the alarm DAC has placed on the device."""
        if not self.enabled:
            return
        stored = await self.stored_alarm()
        if stored:
            await self.async_send_text(ALEXA_CLEAR_TEXT.format(time=stored))
        self._last_placed = None
        await self._async_write_helper("")

    async def async_on_stop(self) -> None:
        """Stop the wake loop – kill device alarm, gate and helper text."""
        await self.async_clear_pre_alarm()
        await self.async_clear_own()
        await self.async_set_gate(False)

    # ------------------------------------------------------------- pre-alarm
    async def async_pre_alarm(self) -> None:
        """Place a fresh short device alarm while the wake loop rings."""
        if not self.enabled:
            return
        time_text = self.pre_alarm_time_text()
        if time_text == self._last_pre_alarm_time:
            return
        self._last_pre_alarm_time = time_text
        self._pre_alarm = parse_time_str(time_text)
        await self.async_send_text(self._set_command(self._pre_alarm))

    async def async_clear_pre_alarm(self) -> None:
        """Delete the short pre-alarm placed while the wake loop was ringing."""
        if not self.enabled or self._pre_alarm is None:
            return
        value = self._pre_alarm
        self._pre_alarm = None
        self._last_pre_alarm_time = None
        await self.async_send_text(ALEXA_CLEAR_TEXT.format(time=format_alexa_time(value)))

    def pre_alarm_time_text(self) -> str:
        """The time string used for the pre-alarm command."""
        pre = self.pre_alarm_minutes
        now = datetime.now().astimezone()
        if pre:
            shifted = now.replace(second=0, microsecond=0) + timedelta(minutes=pre)
            if shifted.date() == now.date():
                return format_alexa_time(shifted.time())
        return format_alexa_time(now.time())

    # ----------------------------------------------------------------- speak
    async def async_speak(self, text: str, volume: int | None = None) -> bool:
        """Speak a short message on the Echo (lowered volume, restored after)."""
        if not self.enabled or not text:
            return False
        player = self.player
        target = (volume or self.reminder_volume) / 100
        previous = await self._current_volume()
        try:
            if previous is not None:
                await ha.call_service(
                    "media_player",
                    "volume_set",
                    {"entity_id": player, "volume_level": target},
                )
            await ha.call_service(
                "notify",
                "alexa_media",
                {"message": text, "data": {"type": "tts"}, "target": [player]},
            )
        except HomeAssistantError as err:
            log.warning("DAC could not speak on %s: %s", player, err)
            return False
        finally:
            if previous is not None:
                self.coordinator.schedule_volume_restore(player, previous)
        return True

    @property
    def reminder_volume(self) -> int:
        """Volume (percent) used for the spoken reminder."""
        try:
            value = int(settings.get("reminder_alexa_volume", 15))
        except (TypeError, ValueError):
            value = 15
        return max(1, min(100, value))

    async def _current_volume(self) -> float | None:
        """Current volume level of the Echo (None when unknown)."""
        if not self.player:
            return None
        state = await ha.state(self.player)
        if state is None:
            return None
        try:
            return float((state.get("attributes") or {}).get("volume_level"))
        except (TypeError, ValueError):
            return None
