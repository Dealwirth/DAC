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

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .const import (
    ALEXA_SET_TEXT,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_MEDIA_PLAYERS,
    CONF_PRE_ALARM_MINUTES,
    DEFAULT_ALEXA_ENABLED_BOOLEAN,
    DEFAULT_ALEXA_TEXT_HELPER,
    DEFAULT_PRE_ALARM_MINUTES,
)
from .logic import alexa_clear_text, alexa_set_text, format_alexa_time, parse_time_str

if TYPE_CHECKING:
    from .coordinator import DacCoordinator

_LOGGER = logging.getLogger(__name__)


class AlexaBridge:
    """Manage the single Alexa device alarm that DAC owns."""

    def __init__(self, hass: HomeAssistant, coordinator: DacCoordinator) -> None:
        self.hass = hass
        self.coordinator = coordinator

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
    def pre_alarm_minutes(self) -> int:
        try:
            return max(0, int(self._options.get(CONF_PRE_ALARM_MINUTES, DEFAULT_PRE_ALARM_MINUTES)))
        except (TypeError, ValueError):
            return DEFAULT_PRE_ALARM_MINUTES

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
                shifted = (
                    dt_util.start_of_local_day(today)
                    + timedelta(hours=alarm_time.hour, minutes=alarm_time.minute)
                    - timedelta(minutes=pre)
                )
                if shifted.date() == today:
                    alarm_time = shifted.time()
            desired = format_alexa_time(alarm_time)

        stored = self.stored_alarm()
        if stored == desired:
            return
        if stored:
            await self.async_send_text(alexa_clear_text(parse_time_str(stored)))
        if desired:
            await self.async_send_text(alexa_set_text(parse_time_str(desired)))
        await self._async_write_helper(desired or "")

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
        try:
            await self.hass.services.async_call(
                "input_boolean", "turn_off", {"entity_id": self.gate_boolean}, blocking=True
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("DAC could not turn off %s: %s", self.gate_boolean, err)

    # ------------------------------------------------------------- pre-alarm
    async def async_pre_alarm(self) -> None:
        """Place a fresh 2-minute device alarm while the wake loop rings."""
        if not self.enabled or not self.gate_on():
            return
        text = ALEXA_SET_TEXT.format(
            time=self.pre_alarm_time_text(), tod=self.pre_alarm_tod()
        )
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
        from .logic import split_am_pm

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
        """Send a text command to the Echo device."""
        player = self.player
        if not player:
            return
        try:
            await self.hass.services.async_call(
                "media_player",
                "play_media",
                {
                    "entity_id": player,
                    "media_content_type": "tts",
                    "media_content_id": text,
                },
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 – Alexa must never break DAC
            _LOGGER.warning("DAC Alexa command failed (%s): %s", player, err)

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
