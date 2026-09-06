"""Shared coordinator and alarm state machine for DAC – Dynamic Alarm Clock.

The coordinator owns the full alarm lifecycle:

* scheduling the next alarm (manual work time or default fallback)
* vacation / holiday suppression via calendars (daily 00:01 scan)
* the looping alarm (lights + media players every 5 minutes)
* the daily reminder when no work time was set (e.g. 20:30)
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
import logging
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALARM_LIGHTS,
    CONF_ALARM_VOLUME,
    CONF_DEFAULT_ALARM_TIME,
    CONF_MEDIA_PLAYERS,
    CONF_NOTIFIER,
    CONF_OFFSET,
    CONF_REMINDER_TEXT,
    CONF_REMINDER_TIME,
    CONF_VACATION_CALENDARS,
    DEFAULT_ALARM_VOLUME,
    DEFAULT_LOOP_INTERVAL,
    DEFAULT_REMINDER_TEXT,
    DEFAULT_VACATION_SCAN_TIME,
    DOMAIN,
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
from .logic import (
    compute_alarm_time,
    default_resolution,
    event_marks_vacation,
    next_occurrence,
    parse_time_str,
)
from .store import DacStore

_LOGGER = logging.getLogger(__name__)

WAKE_TEXT: Final[str] = "Guten Morgen! Es ist Zeit aufzustehen."


class DacCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinate the DAC alarm state machine."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        store: DacStore | None = None,
    ) -> None:
        """Initialize the coordinator and the daily schedules."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=f"{DOMAIN}_{config_entry.entry_id}",
            update_interval=None,
        )
        self.entry_id = config_entry.entry_id
        self._store = store
        self._options = dict(config_entry.options)
        self._unsub: list[Callable[[], None]] = []

        # runtime state (use set_state so listeners are notified)
        self._work_time: time | None = None       # manual work start
        self._work_time_day: date | None = None   # day the manual time belongs to
        self._alarm_day: date | None = None
        self._alarm_time: time | None = None
        self._alarm_target: datetime | None = None
        self._set_state(STATE_IDLE)
        self._last_vacation_day: date | None = None
        self._is_vacation: bool = False
        self._dismissed_days: set[date] = set()
        self._stopped_days: set[date] = set()
        self._vacation_override_day: date | None = None
        self._loop_unsub: Callable[[], None] | None = None
        self._ringing_jobs: list[Callable[[], None]] = []

        self._schedule_daily_jobs()
        # First schedule computation happens in __init__.py after Store restore.

    # ------------------------------------------------------------------ data
    @property
    def options(self) -> dict[str, Any]:
        """Current (updated) options."""
        return self._options

    @callback
    def async_set_options(self, options: dict[str, Any]) -> None:
        """Apply new options and re-evaluate the schedule."""
        self._options = dict(options)
        self._schedule_daily_jobs()
        self._reschedule_alarm()
        self.async_update_listeners()

    @property
    def data(self) -> dict[str, Any]:  # type: ignore[override]
        """Snapshot exposed to entities."""
        return self._snapshot()

    @data.setter
    def data(self, value: dict[str, Any]) -> None:
        """Accept base-class refresh writes (snapshot is computed live)."""

    @callback
    def _set_state(self, state: str) -> None:
        """Update the internal state machine value."""
        self._state = state

    def _snapshot(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "work_time": self._work_time.strftime("%H:%M:%S") if self._work_time else None,
            "work_time_day": self._work_time_day.isoformat() if self._work_time_day else None,
            "alarm_time": self._alarm_time.strftime("%H:%M:%S") if self._alarm_time else None,
            "alarm_day": self._alarm_day.isoformat() if self._alarm_day else None,
            "alarm_target": dt_util.as_local(self._alarm_target).isoformat()
            if self._alarm_target
            else None,
            "vacation": self._is_vacation,
            "mode": self.current_mode,
            "offset_minutes": self.offset_minutes,
            "default_alarm_time": self.default_alarm_time.strftime("%H:%M:%S"),
        }

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh the exposed snapshot (entities poll us)."""
        return self._snapshot()

    # --------------------------------------------------------------- helpers
    @property
    def default_alarm_time(self) -> time:
        """Configured fallback alarm time."""
        return parse_time_str(self._options.get(CONF_DEFAULT_ALARM_TIME, "06:00"))

    @property
    def cutoff_time(self) -> time:
        """Time until which a manual work time may still arrive for tomorrow."""
        return parse_time_str(self._options.get(CONF_REMINDER_TIME, "20:30"))

    @property
    def offset_minutes(self) -> int:
        """Minutes between alarm and work start."""
        try:
            return int(self._options.get(CONF_OFFSET, 60))
        except (TypeError, ValueError):
            return 60

    def _notif_message(self) -> str:
        template = self._options.get(CONF_REMINDER_TEXT) or DEFAULT_REMINDER_TEXT
        default_t = self._options.get(CONF_DEFAULT_ALARM_TIME, "06:00")
        try:
            return str(template).format(alarm_time=default_t)
        except (KeyError, IndexError, ValueError):
            return str(template)

    # ------------------------------------------------------- public services
    async def async_set_work_time(self, call: ServiceCall) -> None:
        """Handle dac.set_work_time (also wired for NFC tag scans)."""
        await self._async_set_work_time_impl(call)
        await self.async_save_state()

    async def _async_set_work_time_impl(self, call: ServiceCall) -> None:
        now = dt_util.now()
        raw_time = call.data.get("time")
        work_time = parse_time_str(raw_time) if raw_time else None
        clear = bool(call.data.get("clear"))

        if clear and work_time is None:
            self._work_time = None
            self._work_time_day = None
        elif work_time is None:
            raise HomeAssistantError("Either 'time' or 'clear' must be provided")
        else:
            day_raw = call.data.get("day")
            if day_raw:
                work_day = date.fromisoformat(str(day_raw))
            else:
                # An evening scan (>= cutoff) targets tomorrow; otherwise today.
                work_day = now.date() + (
                    timedelta(days=1) if now.time() >= self.cutoff_time else timedelta(0)
                )
            self._work_time = work_time
            self._work_time_day = work_day
            self._dismissed_days.discard(work_day)
            self._stopped_days.discard(work_day)

        await self._async_stop_loop()
        self._reschedule_alarm()
        self.async_update_listeners()

    async def async_stop_alarm(self, call: ServiceCall) -> None:
        """Stop the looping alarm now."""
        if self._state == STATE_RINGING:
            self._stopped_days.add(dt_util.now().date())
            await self._async_stop_loop(set_state=STATE_STOPPED)
        else:
            await self._async_stop_loop()
        await self.async_save_state()

    async def async_dismiss_for_today(self, call: ServiceCall) -> None:
        """Disable the alarm for the current / upcoming day."""
        now = dt_util.now()
        day_raw = call.data.get("day")
        if day_raw:
            target_day = date.fromisoformat(str(day_raw))
        elif self._alarm_day is not None and self._alarm_target and now > self._alarm_target:
            target_day = self._alarm_day
        else:
            target_day = now.date()
        await self._async_dismiss_for(target_day)

    async def _async_dismiss_for(self, target_day: date) -> None:
        """Internal dismiss for a specific day."""
        self._dismissed_days.add(target_day)
        await self._async_stop_loop(set_state=STATE_DISMISSED)
        self._reschedule_alarm()
        self.async_update_listeners()
        await self.async_save_state()

    async def async_set_mode(self, mode: str) -> None:
        """Set the alarm mode from the select entity."""
        today = dt_util.now().date()
        if mode == MODE_VACATION:
            self._vacation_override_day = today
            await self._async_vacation_check()
        elif mode == MODE_DISMISSED:
            self._vacation_override_day = None
            # Re-evaluate vacation state from calendars before dismissing.
            await self._async_vacation_check()
            await self._async_dismiss_for(today)
        else:  # MODE_STANDARD
            self._vacation_override_day = None
            self._dismissed_days.discard(today)
            # Re-evaluate vacation state from calendars (clears stale overrides).
            await self._async_vacation_check()
        await self.async_save_state()

    @property
    def current_mode(self) -> str:
        """Currently active mode for the select entity."""
        today = dt_util.now().date()
        if self._vacation_override_day == today or self._is_vacation:
            return MODE_VACATION
        if today in self._dismissed_days:
            return MODE_DISMISSED
        return MODE_STANDARD

    # -------------------------------------------------------------- storage
    def _storage_payload(self) -> dict[str, Any]:
        """Serialize the mutable state for the Store."""
        return {
            "work_time": self._work_time.strftime("%H:%M:%S") if self._work_time else None,
            "work_time_day": self._work_time_day.isoformat() if self._work_time_day else None,
            "state": self._state,
            "alarm_day": self._alarm_day.isoformat() if self._alarm_day else None,
            "alarm_target": self._alarm_target.isoformat() if self._alarm_target else None,
            "dismissed": sorted(d.isoformat() for d in self._dismissed_days),
            "stopped": sorted(d.isoformat() for d in self._stopped_days),
        }

    async def async_save_state(self) -> None:
        """Persist the current state (called after every mutation)."""
        if self._store is None:
            return
        try:
            await self._store.async_save(self._storage_payload())
        except (OSError, ValueError) as err:
            _LOGGER.warning("DAC could not persist state: %s", err)

    async def async_restore_state(self, data: dict[str, Any]) -> None:
        """Restore persisted state after a restart and resume if ringing."""
        try:
            if data.get("work_time"):
                self._work_time = parse_time_str(data["work_time"])
                self._work_time_day = (
                    date.fromisoformat(data["work_time_day"]) if data.get("work_time_day") else None
                )
                if self._work_time_day and self._work_time_day < dt_util.now().date():
                    self._work_time = None
                    self._work_time_day = None
            self._dismissed_days = {
                date.fromisoformat(d)
                for d in data.get("dismissed") or []
                if date.fromisoformat(d) >= dt_util.now().date()
            }
            self._stopped_days = {
                date.fromisoformat(d)
                for d in data.get("stopped") or []
                if date.fromisoformat(d) >= dt_util.now().date()
            }
            if data.get("alarm_day"):
                self._alarm_day = date.fromisoformat(data["alarm_day"])
            saved_state = data.get("state")
        except (ValueError, TypeError) as err:
            _LOGGER.warning("DAC could not restore state: %s", err)
            self._reschedule_alarm()
            return

        # Resume a ringing alarm if HA restarted during the alarm window.
        if (
            saved_state == STATE_RINGING
            and self._alarm_day == dt_util.now().date()
            and data.get("alarm_target")
        ):
            try:
                target = dt_util.parse_datetime(data["alarm_target"])
            except (ValueError, TypeError):
                target = None
            if target and dt_util.now() - target <= timedelta(hours=1):
                self._set_state(STATE_RINGING)
                self.async_update_listeners()
                await self._async_fire_once()
                if self._state == STATE_RINGING:
                    self._loop_unsub = async_track_time_interval(
                        self.hass, self._loop_tick, DEFAULT_LOOP_INTERVAL
                    )
                return
        self._reschedule_alarm()

    # ------------------------------------------------------------ scheduling
    @callback
    def _schedule_daily_jobs(self) -> None:
        """(Re)create the daily 00:01 vacation scan and the reminder job."""
        for unsub in self._unsub:
            unsub()
        self._unsub = []

        scan_h, scan_m = _split_time(DEFAULT_VACATION_SCAN_TIME)
        self._unsub.append(
            async_track_time_change(
                self.hass, self._vacation_scan, hour=scan_h, minute=scan_m, second=0
            )
        )
        rem_h, rem_m = _split_time(self._options.get(CONF_REMINDER_TIME, "20:30"))
        self._unsub.append(
            async_track_time_change(
                self.hass, self._reminder_check, hour=rem_h, minute=rem_m, second=0
            )
        )
        # Run a vacation check right away (e.g. after a restart).
        self.hass.async_create_task(self._async_vacation_check())

    @callback
    def _vacation_scan(self, now: datetime) -> None:
        self.hass.async_create_task(self._async_vacation_check(save=True))

    async def _async_vacation_check(self, save: bool = False) -> None:
        """Check calendars for vacation/holiday events covering today."""
        today = dt_util.now().date()
        calendars: list[str] = list(self._options.get(CONF_VACATION_CALENDARS) or [])
        vacation = False
        if calendars:
            try:
                result = await self.hass.services.async_call(
                    "calendar",
                    "get_events",
                    {
                        "entity_id": calendars,
                        "start_date_time": dt_util.start_of_local_day(today),
                        "end_date_time": dt_util.start_of_local_day(today) + timedelta(days=1),
                    },
                    blocking=True,
                    return_response=True,
                )
                events: list[dict[str, Any]] = []
                for response in result.values():
                    events.extend(response.get("events") or [])
                vacation = any(event_marks_vacation(ev, today) for ev in events)
            except (HomeAssistantError, ValueError) as err:
                _LOGGER.warning("DAC vacation check failed: %s", err)
        if self._vacation_override_day == today:
            vacation = True
        self._is_vacation = vacation
        self._last_vacation_day = today
        if vacation and self._state in (STATE_SCHEDULED, STATE_IDLE):
            self._set_state(STATE_VACATION)
        self._reschedule_alarm()
        self.async_update_listeners()
        if save:
            await self.async_save_state()

    @callback
    def _reminder_check(self, now: datetime) -> None:
        self.hass.async_create_task(self._async_reminder_check(now))

    async def _async_reminder_check(self, now: datetime) -> None:
        """Send the reminder if no work time was set for tomorrow (or today)."""
        if self._is_vacation:
            return
        tomorrow = now.date() + timedelta(days=1)
        scheduled_for = self._work_time_day or self._alarm_day
        if scheduled_for in (now.date(), tomorrow):
            return  # a work time is already set
        if self._state == STATE_RINGING:
            return
        notifier = self._options.get(CONF_NOTIFIER)
        if not notifier:
            return
        domain, _, service = str(notifier).partition(".")
        if domain != "notify":
            domain, service = "notify", str(notifier)
        message = self._notif_message()
        try:
            await self.hass.services.async_call(
                domain, service, {"message": message}, blocking=True
            )
        except HomeAssistantError as err:
            _LOGGER.warning("DAC reminder via %s failed: %s", notifier, err)

    # --------------------------------------------------------- alarm runtime
    @callback
    def _reschedule_alarm(self) -> None:
        """Compute the next alarm and (re)arm the point-in-time trigger."""
        for job in self._ringing_jobs:
            job()
        self._ringing_jobs = []

        if self._is_vacation:
            self._set_state(STATE_VACATION)
            self._alarm_target = None
            return

        now = dt_util.now()
        if now.date() in self._dismissed_days and (
            self._alarm_day is None or self._alarm_day <= now.date()
        ):
            self._set_state(STATE_DISMISSED)

        work_time = self._work_time
        if (
            work_time is not None
            and self._work_time_day == now.date()
            and now.time() > work_time
            and self._state in (STATE_STOPPED, STATE_DISMISSED)
        ):
            # Today's alarm already fired and was stopped/dismissed: the manual
            # time is consumed and the *next* alarm comes from the fallback.
            work_time = None

        if work_time is not None:
            if self._work_time_day is not None:
                candidate = datetime.combine(
                    self._work_time_day, work_time, tzinfo=now.tzinfo
                )
                if candidate <= now and self._work_time_day == now.date():
                    candidate = next_occurrence(now, work_time)
                self._alarm_day = candidate.date()
            else:
                candidate = next_occurrence(now, work_time)
                self._alarm_day = candidate.date()
            self._alarm_time = work_time
        else:
            day, t = default_resolution(now, self.default_alarm_time, self.cutoff_time)
            if day is None or t is None:
                if self._state != STATE_DISMISSED:
                    self._set_state(STATE_IDLE)
                self._alarm_time = None
                self._alarm_day = None
                self._alarm_target = None
                return
            self._alarm_day = day
            self._alarm_time = t

        if self._alarm_day in self._dismissed_days:
            self._set_state(STATE_DISMISSED)
            self._alarm_target = None
            return

        self._alarm_target = datetime.combine(
            self._alarm_day,
            compute_alarm_time(self._alarm_time, self.offset_minutes),
            tzinfo=now.tzinfo,
        )
        if self._alarm_target <= now:
            self._alarm_target += timedelta(days=1)
            self._alarm_day += timedelta(days=1)

        if self._state not in (STATE_RINGING, STATE_STOPPED, STATE_DISMISSED):
            self._set_state(STATE_SCHEDULED)
        self._ringing_jobs.append(
            async_track_point_in_time(self.hass, self._alarm_fired, self._alarm_target)
        )
        _LOGGER.debug(
            "DAC alarm scheduled: day=%s work=%s target=%s state=%s",
            self._alarm_day,
            self._alarm_time,
            self._alarm_target,
            self._state,
        )

    async def _alarm_fired(self, now: datetime) -> None:
        """The alarm time has been reached – start the looping alarm."""
        if self._is_vacation or self._alarm_day in self._dismissed_days:
            self._set_state(STATE_VACATION if self._is_vacation else STATE_DISMISSED)
            return
        self._set_state(STATE_RINGING)
        self.async_update_listeners()
        await self._async_fire_once()
        if self._state == STATE_RINGING:
            self._loop_unsub = async_track_time_interval(
                self.hass, self._loop_tick, DEFAULT_LOOP_INTERVAL
            )

    async def _loop_tick(self, now: datetime) -> None:
        if self._state != STATE_RINGING:
            return
        await self._async_fire_once()

    async def _async_fire_once(self) -> None:
        """One loop iteration: lights on + media players announce."""
        lights = list(self._options.get(CONF_ALARM_LIGHTS) or [])
        players = list(self._options.get(CONF_MEDIA_PLAYERS) or [])
        for light in lights:
            state = self.hass.states.get(light)
            if state is None or state.state == "off":
                try:
                    await self.hass.services.async_call(
                        "light", "turn_on", {"entity_id": light}, blocking=True
                    )
                except HomeAssistantError as err:
                    _LOGGER.warning("DAC could not turn on %s: %s", light, err)
        for player in players:
            try:
                await self.hass.services.async_call(
                    "media_player",
                    "volume_set",
                    {"entity_id": player, "volume_level": self._volume},
                    blocking=True,
                )
                await self.hass.services.async_call(
                    "media_player",
                    "play_media",
                    {
                        "entity_id": player,
                        "media_content_type": "tts",
                        "media_content_id": WAKE_TEXT,
                    },
                    blocking=True,
                )
            except HomeAssistantError as err:
                _LOGGER.warning("DAC could not alarm on %s: %s", player, err)

    @property
    def _volume(self) -> float:
        try:
            return max(
                0.0, min(1.0, float(self._options.get(CONF_ALARM_VOLUME, DEFAULT_ALARM_VOLUME)))
            )
        except (TypeError, ValueError):
            return DEFAULT_ALARM_VOLUME

    async def _async_stop_loop(self, set_state: str | None = None) -> None:
        """Stop media players and the repeating loop."""
        if self._loop_unsub:
            self._loop_unsub()
            self._loop_unsub = None
        for job in self._ringing_jobs:
            job()
        self._ringing_jobs = []
        players = list(self._options.get(CONF_MEDIA_PLAYERS) or [])
        for player in players:
            try:
                await self.hass.services.async_call(
                    "media_player", "media_stop", {"entity_id": player}, blocking=True
                )
            except HomeAssistantError as err:
                _LOGGER.debug("DAC could not stop %s: %s", player, err)
        if set_state:
            self._set_state(set_state)

    def async_shutdown(self) -> None:
        """Tear down all timers (called on entry unload)."""
        for unsub in self._unsub:
            unsub()
        self._unsub = []
        if self._loop_unsub:
            self._loop_unsub()
            self._loop_unsub = None
        for job in self._ringing_jobs:
            job()
        self._ringing_jobs = []
        self.hass.async_create_task(super().async_shutdown())


def _split_time(value: str | time) -> tuple[int, int]:
    t = parse_time_str(value)
    return t.hour, t.minute
