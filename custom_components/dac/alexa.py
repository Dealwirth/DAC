"""Optional device alarms on Amazon Echo (via the alexa_media integration).

DAC can additionally set a *real* alarm on the Echo device itself:

* The command is sent as text (``media_player.play_media`` with
  ``media_content_type: tts``) and always contains "morgens"/"abends" so
  Alexa never asks back for the time of day.
* Only the alarm DAC itself has set (stored in an ``input_text`` helper) is
  ever deleted – manually configured Echo alarms are left untouched.
* While the wake loop is ringing, a fresh 2-minute pre-alarm is placed on
  the device every loop iteration (as long as the ``input_boolean`` gate is
  on), so the Echo also rings if Home Assistant is unavailable.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    ALEXA_COMMAND_TYPE_CUSTOM,
    ALEXA_COMMAND_TYPE_TTS,
    ALEXA_STOP_ALARM_TEXT,
    ATTR_DAY,
    ATTR_TIME,
    CONF_ALEXA_COMMAND_TYPE,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_MEDIA_PLAYERS,
    CONF_PRE_ALARM_MINUTES,
    CONF_STOP_WORD,
    DEFAULT_ALEXA_ENABLED_BOOLEAN,
    DEFAULT_ALEXA_TEXT_HELPER,
    DEFAULT_PRE_ALARM_MINUTES,
    DEFAULT_STOP_WORD,
)
from .logic import (
    alexa_clear_text,
    alexa_set_text,
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
        """The Echo media_player entity (falls back to the alarm players)."""
        player = self._options.get(CONF_ALEXA_MEDIA_PLAYER)
        if player:
            return str(player)
        players = self._options.get(CONF_MEDIA_PLAYERS) or []
        return str(players[0]) if players else None

    @property
    def helper(self) -> str:
        return str(self._options.get(CONF_ALEXA_TEXT_HELPER) or DEFAULT_ALEXA_TEXT_HELPER)

    @property
    def gate_boolean(self) -> str:
        return str(self._options.get(CONF_ALEXA_ENABLED_BOOLEAN) or DEFAULT_ALEXA_ENABLED_BOOLEAN)

    @property
    def command_type(self) -> str:
        """How the text command is sent: 'custom' (text command) or 'tts'."""
        value = self._options.get(CONF_ALEXA_COMMAND_TYPE)
        return value if value in (ALEXA_COMMAND_TYPE_CUSTOM, ALEXA_COMMAND_TYPE_TTS) else ALEXA_COMMAND_TYPE_CUSTOM

    @property
    def pre_alarm_minutes(self) -> int:
        try:
            return max(0, int(self._options.get(CONF_PRE_ALARM_MINUTES, DEFAULT_PRE_ALARM_MINUTES)))
        except (TypeError, ValueError):
            return DEFAULT_PRE_ALARM_MINUTES

    @property
    def stop_word(self) -> str:
        """Label used for the Echo alarms so an Alexa routine can stop DAC.

        DAC names every alarm it places on the device with this label. In the
        Alexa app the user creates one routine ("DAC Stopp") whose trigger is
        "when an alarm with this name rings" and whose action calls the HA
        script/service ``dac.stop_alarm`` – no custom skill and no cloud hook
        required, and it works even if Home Assistant is briefly offline.
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

    # ------------------------------------------------------------------ sync
    async def async_sync(self) -> None:
        """Reconcile the device alarm with the currently computed DAC alarm."""
        if not self.enabled:
            return
        coordinator = self.coordinator
        today = dt_util.now().date()

        desired: str | None = None
        if (
            not coordinator._is_vacation
            and coordinator._state != "ringing"
            and coordinator._alarm_day == today
            and coordinator._alarm_time is not None
            and today not in coordinator._dismissed_days
        ):
            alarm_time = coordinator._alarm_time
            pre = self.pre_alarm_minutes
            if pre:
                # Only shift into the past if it stays on the same day; a
                # negative shift across midnight would set a wrong-day alarm.
                shifted = (
                    dt_util.start_of_local_day(today)
                    + timedelta(hours=alarm_time.hour, minutes=alarm_time.minute)
                    - timedelta(minutes=pre)
                )
                if shifted.date() == today and shifted.time() < alarm_time:
                    alarm_time = shifted.time()
            desired = format_alexa_time(alarm_time)

        stored = self.stored_alarm()
        if stored == desired:
            return
        if stored:
            await self.async_send_text(alexa_clear_text(parse_time_str(stored)))
        if desired:
            await self.async_send_text(self._set_command(parse_time_str(desired)))
        await self._async_write_helper(desired or "")

    async def async_set_alarm(self, call: ServiceCall | Any) -> None:
        """Handle dac.set_alexa_alarm – optional explicit time/day override.

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
        await self.async_clear_own()
        await self.async_set_gate(False)

    # ------------------------------------------------------------- pre-alarm
    def _set_command(self, value: Any) -> str:
        """The 'set an alarm' command, labelled with the stop word when set.

        The label is what an Alexa routine can listen for ("when an alarm
        named 'Wecker aus' rings -> call dac.stop_alarm"), so stopping the
        alarm by voice needs no custom skill.
        """
        base = alexa_set_text(value)
        label = self.stop_word
        if not label:
            return base
        return ALEXA_STOP_ALARM_TEXT.format(
            time=format_alexa_time(value), tod=split_am_pm(value), label=label
        )

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
        text = self._set_command(parse_time_str(time_text))
        await self.async_send_text(text)

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

    def pre_alarm_tod(self) -> str:
        """'morgens'/'abends' for the pre-alarm time."""
        alarm_time = self.coordinator._alarm_time or dt_util.now().time()
        pre = self.pre_alarm_minutes
        if pre:
            now = dt_util.now()
            shifted = now.replace(second=0, microsecond=0) + timedelta(minutes=pre)
            if shifted.date() == now.date():
                return split_am_pm(shifted.time())
        return split_am_pm(alarm_time)

    # ------------------------------------------------------------------ io
    async def async_send_text(self, text: str) -> None:
        """Send a text command to the Echo device.

        ``custom`` sends it as a plain Alexa text command (the classic YAML
        way), ``tts`` lets the device speak it. Both carry the alarm phrasing.
        """
        player = self.player
        if not player:
            return
        try:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": player,
                    "media_content_type": self.command_type,
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
