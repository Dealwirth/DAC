"""Device alarm on Amazon Echo (via the alexa_media integration).

DAC places a *real* alarm on the Echo device, exactly like the YAML
automation: a text command ("stelle einen Wecker auf 05:00 Uhr morgens") is
sent with ``media_player.play_media`` and ``media_content_type: custom``.
The AM/PM suffix stops Alexa from asking back for the time of day.

* Only the alarm DAC itself has set (stored in an ``input_text`` helper) is
  ever deleted – manually configured Echo alarms are left untouched.
* While the wake loop is ringing, a fresh short pre-alarm is placed on the
  device on every loop iteration, so the Echo also rings if Home Assistant
  is unavailable.
* Every alarm DAC places carries the configurable stop word as its name. An
  Alexa routine triggered by "an alarm with this name rings" can call
  ``dac.stop_alarm`` – stopping by voice needs no custom skill.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    ALEXA_SET_NAMED_TEXT,
    ALEXA_SET_PLAIN_TEXT,
    ATTR_DAY,
    ATTR_TIME,
    CONF_ALEXA_ALARM_NAME,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_PRE_ALARM_MINUTES,
    CONF_REMINDER_ALEXA_VOLUME,
    CONF_STOP_WORD,
    DEFAULT_ALEXA_ENABLED_BOOLEAN,
    DEFAULT_ALEXA_TEXT_HELPER,
    DEFAULT_PRE_ALARM_MINUTES,
    DEFAULT_STOP_WORD,
)
from .logic import (
    alexa_clear_text,
    format_alexa_time,
    parse_time_str,
    split_am_pm,
)

if TYPE_CHECKING:
    from .coordinator import DacCoordinator

_LOGGER = logging.getLogger(__name__)


class AlexaBridge:
    """Manage the single Alexa device alarm that DAC owns."""

    def __init__(self, hass: HomeAssistant, coordinator: DacCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator
        self._last_pre_alarm_time: Any = None
        self._pre_alarm: Any = None
        # Serialise syncs: set_work_time triggers a background sync while the
        # service may await one too – without this the alarm is placed twice.
        self._sync_lock = asyncio.Lock()

    # ----------------------------------------------------------------- config
    @property
    def _options(self) -> dict[str, Any]:
        return self.coordinator.options

    @property
    def enabled(self) -> bool:
        """True when the Alexa integration is switched on and a player is set."""
        if not bool(self._options.get(CONF_ALEXA_ENABLED, False)):
            return False
        return bool(self.player)

    @property
    def player(self) -> str | None:
        """The Echo media_player entity."""
        player = self._options.get(CONF_ALEXA_MEDIA_PLAYER)
        return str(player) if player else None

    @property
    def helper(self) -> str:
        return str(self._options.get(CONF_ALEXA_TEXT_HELPER) or DEFAULT_ALEXA_TEXT_HELPER)

    @property
    def gate_boolean(self) -> str:
        return str(self._options.get(CONF_ALEXA_ENABLED_BOOLEAN) or DEFAULT_ALEXA_ENABLED_BOOLEAN)

    @property
    def pre_alarm_minutes(self) -> int:
        try:
            return max(0, int(self._options.get(CONF_PRE_ALARM_MINUTES, DEFAULT_PRE_ALARM_MINUTES)))
        except (TypeError, ValueError):
            return DEFAULT_PRE_ALARM_MINUTES

    @property
    def stop_word(self) -> str:
        """Name given to the Echo alarms so an Alexa routine can stop DAC.

        In the Alexa app the user creates one routine ("DAC Stopp") whose
        trigger is "when an alarm with this name rings" and whose action calls
        ``dac.stop_alarm`` – no custom skill and no cloud hook required.
        """
        value = str(self._options.get(CONF_STOP_WORD) or DEFAULT_STOP_WORD).strip()
        return value or DEFAULT_STOP_WORD

    # ------------------------------------------------------------------ state
    def gate_on(self) -> bool:
        """True while the user's wecker_aktiv input_boolean is on."""
        state = self.hass.states.get(self.gate_boolean)
        return bool(state) and state.state == "on"

    def stored_alarm(self) -> str | None:
        """The alarm time DAC has placed on the device ('HH:MM' or None)."""
        state = self.hass.states.get(self.helper)
        if not state or not state.state or state.state in ("unknown", "unavailable", "none"):
            return None
        try:
            parse_time_str(state.state)
        except ValueError:
            return None
        return format_alexa_time(parse_time_str(state.state))

    def device_has_alarm(self, time_text: str) -> bool:
        """True when the Echo really has an active alarm at ``time_text``.

        Reads the ``sensor.<player>_next_alarm`` state the alexa_media
        integration exposes and looks for a future alarm whose time matches.
        The sensor is refreshed by alexa_media itself; when it is missing the
        method returns True so a forced sync is not triggered on every refresh.
        """
        object_id = str(self.player or "").split(".", 1)[-1]
        if not object_id:
            return True
        state = self.hass.states.get(f"sensor.{object_id}_next_alarm")
        if state is None:
            return True
        try:
            want = parse_time_str(time_text).strftime("%H:%M")
        except ValueError:
            return True
        now = dt_util.now()
        for alarm in state.attributes.get("sorted_all") or []:
            if alarm.get("status") != "ON":
                continue
            raw = alarm.get("date_time")
            if not raw:
                continue
            try:
                when = dt_util.parse_datetime(str(raw))
            except (ValueError, TypeError):
                continue
            if when is None or when < now:
                continue
            if when.strftime("%H:%M") == want:
                return True
        return False

    # ------------------------------------------------------------------ sync
    async def async_sync(self, *, force: bool = False) -> None:
        """Reconcile the device alarm with the currently computed DAC alarm.

        The Echo alarm is placed for the *next* alarm – today **or** tomorrow.
        A work time is normally set in the evening and therefore targets the
        next morning; restricting this to "today" silently produced no alarm at
        all, so the user was never woken up.

        The ``input_text`` helper only mirrors what DAC *believes* it placed.
        If the device alarm was lost (Alexa app, power cut, another integration)
        the helper still matches the desired time and a plain sync would skip
        the placement – so the wake-up would silently not happen. ``force``
        re-places the alarm and is used when the Echo alarm is known to be gone.
        """
        if not self.enabled:
            return
        async with self._sync_lock:
            desired = self._desired_alarm_text()
            stored = self.stored_alarm()
            if stored == desired and not force:
                return
            if stored:
                await self.async_send_text(alexa_clear_text(parse_time_str(stored)))
            if desired:
                await self.async_send_text(self._set_command(parse_time_str(desired)))
            await self._async_write_helper(desired or "")

    async def async_ensure_scheduled(self) -> None:
        """Make sure the scheduled alarm really exists on the Echo device.

        Runs on every coordinator refresh. If the device alarm matching the
        stored helper time is gone, the alarm is re-placed (forced sync). This
        closes the "helper says 05:44, Echo has no active alarm" gap that left
        the user without a wake-up.
        """
        if not self.enabled:
            return
        desired = self._desired_alarm_text()
        if not desired:
            # Nothing should ring – make sure no stale DAC alarm is left over.
            await self.async_sync()
            return
        if self.device_has_alarm(desired):
            return
        _LOGGER.info(
            "DAC: Echo alarm %s is missing on %s – re-placing it", desired, self.player
        )
        await self.async_sync(force=True)

    def _desired_alarm_text(self) -> str | None:
        """The device alarm DAC currently wants on the Echo ('HH:MM' or None).

        None only when there must be no alarm at all (vacation, dismissed,
        ringing, or nothing scheduled). The concrete day is irrelevant for the
        Echo – it only knows times – so an alarm for tomorrow is placed the
        same way as one for today.
        """
        coordinator = self.coordinator
        if coordinator._is_vacation or coordinator._state == "ringing":
            return None
        if coordinator._alarm_time is None or coordinator._alarm_target is None:
            return None
        if coordinator._alarm_day is not None and coordinator._alarm_day in coordinator._dismissed_days:
            return None

        # The real wake-up moment is ``_alarm_target`` (work time MINUS offset);
        # ``_alarm_time`` is the work start, so using it would ring an hour late.
        target = coordinator._alarm_target
        pre = self.pre_alarm_minutes
        if pre:
            # Only shift into the past if it stays on the same day; a negative
            # shift across midnight would set the alarm on the wrong day.
            shifted = target - timedelta(minutes=pre)
            if shifted.date() == target.date():
                target = shifted
        return format_alexa_time(target.time())

    async def async_set_alarm(self, call: ServiceCall | Any) -> None:
        """Handle dac.set_alexa_alarm – optional explicit time override.

        Without ``time`` the currently computed alarm is (re-)placed on the
        device. With an explicit ``time`` the given alarm is placed directly
        (an existing DAC alarm is removed first).
        """
        if not self.enabled:
            return
        raw_time = call.data.get(ATTR_TIME) if hasattr(call, "data") else None
        if not raw_time:
            await self.async_sync()
            return

        try:
            value = parse_time_str(raw_time)
        except ValueError as err:
            raise HomeAssistantError(f"Invalid time: {raw_time!r}") from err
        text = format_alexa_time(value)

        stored = self.stored_alarm()
        if stored and stored != text:
            await self.async_send_text(alexa_clear_text(parse_time_str(stored)))
        await self.async_send_text(self._set_command(value))
        await self._async_write_helper(text)
        _LOGGER.debug("DAC placed a manual Alexa alarm for %s (%s)", text, call.data.get(ATTR_DAY))

    async def async_clear_own(self) -> None:
        """Delete only the alarm DAC has placed on the device (Tag 4)."""
        if not self.enabled:
            return
        stored = self.stored_alarm()
        if stored:
            await self.async_send_text(alexa_clear_text(parse_time_str(stored)))
        await self._async_write_helper("")

    async def async_on_stop(self) -> None:
        """Tag 4: stop the wake loop – kill device alarm, gate and helper text."""
        await self.async_clear_pre_alarm()
        await self.async_clear_own()
        await self.async_set_gate(False)

    # ------------------------------------------------------------- pre-alarm
    @property
    def alarm_name(self) -> str:
        """Optional name given to the Echo alarm (empty = no name).

        The name is what an Alexa routine listens for ("an alarm named
        'Wecker aus' rings -> call dac.stop_alarm"), so stopping by voice needs
        no custom skill. It is optional: a name can make Alexa ask back or
        refuse the command on some devices, so the default is a plain alarm.
        """
        raw = self._options.get(CONF_ALEXA_ALARM_NAME)
        return str(raw).strip() if raw else ""

    def _set_command(self, value: Any) -> str:
        """The 'set an alarm' command (named only when a name is configured)."""
        time_text = format_alexa_time(value)
        tod = split_am_pm(value)
        name = self.alarm_name
        if name:
            return ALEXA_SET_NAMED_TEXT.format(time=time_text, tod=tod, label=name)
        return ALEXA_SET_PLAIN_TEXT.format(time=time_text, tod=tod)

    async def async_pre_alarm(self) -> None:
        """Place a fresh short device alarm while the wake loop rings.

        Unlike the YAML automation this does not depend on the gate: once the
        alarm fires, the device alarm is re-placed on every loop iteration, so
        the Echo rings even if Home Assistant drops out afterwards.
        """
        if not self.enabled:
            return
        time_text = self.pre_alarm_time_text()
        if time_text == self._last_pre_alarm_time:
            # Same minute as the previous loop iteration – do not spam the Echo
            # with an identical command.
            return
        self._last_pre_alarm_time = time_text
        self._pre_alarm = parse_time_str(time_text)
        await self.async_send_text(self._set_command(parse_time_str(time_text)))

    async def async_clear_pre_alarm(self) -> None:
        """Delete the short pre-alarm placed while the wake loop was ringing.

        The pre-alarm is what actually wakes the user; without deleting it a
        stop would still let the Echo ring a few minutes later. The stored
        input_text helper only tracks the scheduled alarm, so the pre-alarm
        time has to be remembered separately.
        """
        if not self.enabled or self._pre_alarm is None:
            return
        value = self._pre_alarm
        self._pre_alarm = None
        self._last_pre_alarm_time = None
        await self.async_send_text(alexa_clear_text(value))

    def pre_alarm_time_text(self) -> str:
        """The time string used for the pre-alarm command."""
        alarm_time = self.coordinator._alarm_time or dt_util.now().time()
        pre = self.pre_alarm_minutes
        if pre:
            now = dt_util.now()
            shifted = now.replace(second=0, microsecond=0) + timedelta(minutes=pre)
            if shifted.date() == now.date():
                return format_alexa_time(shifted.time())
        return format_alexa_time(alarm_time)

    # ------------------------------------------------------------------ io
    @property
    def reminder_volume(self) -> int:
        """Volume (percent) used for the spoken reminder."""
        try:
            value = int(self._options.get(CONF_REMINDER_ALEXA_VOLUME, 15))
        except (TypeError, ValueError):
            value = 15
        return max(1, min(100, value))

    def _speak_service(self) -> tuple[str, str] | None:
        """Find a notify service that makes the Echo speak (alexa_media)."""
        player = self.player
        if not player:
            return None
        object_id = player.split(".", 1)[1]
        for name in (f"alexa_media_{object_id}", "alexa_media"):
            if self.hass.services.has_service("notify", name):
                return "notify", name
        return None

    async def async_speak(self, text: str, volume: int | None = None) -> bool:
        """Speak a short message on the Echo (no alarm, just a quiet notice).

        The Echo volume is lowered for the message and restored afterwards, so
        a reminder at 21:00 never blasts the room. Returns True when a speak
        service was available.
        """
        if not self.enabled or not text:
            return False
        service = self._speak_service()
        if service is None:
            return False

        player = self.player
        target_volume = (volume or self.reminder_volume) / 100
        previous = self._current_volume()
        try:
            if previous is not None:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": player, "volume_level": target_volume},
                    blocking=True,
                )
            data: dict[str, Any] = {"message": text, "data": {"type": "tts"}}
            if service[1] == "alexa_media":
                data["target"] = [player]
            await self.hass.services.async_call(service[0], service[1], data, blocking=True)
        except Exception as err:  # noqa: BLE001 – a reminder must never break DAC
            _LOGGER.warning("DAC could not speak on %s: %s", player, err)
            return False
        finally:
            if previous is not None:
                self._schedule_volume_restore(player, previous)
        return True

    def _current_volume(self) -> float | None:
        """Current volume level of the Echo (None when unknown)."""
        state = self.hass.states.get(self.player) if self.player else None
        if state is None:
            return None
        value = state.attributes.get("volume_level")
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _schedule_volume_restore(self, player: str, volume: float) -> None:
        """Restore the Echo volume shortly after the spoken reminder."""
        from homeassistant.helpers.event import async_call_later

        async def _restore(_now: Any) -> None:
            try:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": player, "volume_level": volume},
                    blocking=True,
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("DAC could not restore the volume of %s: %s", player, err)

        async_call_later(self.hass, 12, _restore)

    async def async_send_text(self, text: str) -> None:
        """Send a plain Alexa text command to the Echo device."""
        player = self.player
        if not player:
            return
        try:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": player,
                    "media_content_type": "custom",
                    "media_content_id": text,
                },
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 – Alexa must never break DAC
            _LOGGER.warning("DAC Alexa command failed (%s): %s", player, err)

    async def async_set_gate(self, on: bool) -> None:
        """Turn the user's wecker_aktiv input_boolean on/off (like Tag 1/Tag 4).

        No-op unless the Alexa bridge is active, so a setup without the bridge
        never touches the helper.
        """
        if not self.enabled:
            return
        try:
            await self.hass.services.async_call(
                "input_boolean",
                "turn_on" if on else "turn_off",
                {"entity_id": self.gate_boolean},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 – the gate is a safety net only
            _LOGGER.debug("DAC could not set %s: %s", self.gate_boolean, err)

    async def _async_write_helper(self, value: str) -> None:
        """Store the currently placed alarm in the input_text helper."""
        try:
            await self.hass.services.async_call(
                "input_text",
                "set_value",
                {"entity_id": self.helper, "value": value},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("DAC could not update helper %s: %s", self.helper, err)
