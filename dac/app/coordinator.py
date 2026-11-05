"""Alarm state machine and scheduler for the DAC app.

Owns the full alarm lifecycle: computing the next alarm from the work time
minus offset, vacation/holiday suppression from calendars, the repeating wake
loop (lights + Echo pre-alarm), the daily reminder and the Echo watchdog.

A single background task ticks every few seconds and fires whatever is due, so
a restarted app picks the schedule back up immediately.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from .alexa import AlexaBridge
from .config import DATA_DIR, settings
from .ha_client import HomeAssistantError, ha
from .logic import (
    compute_alarm_time,
    default_resolution,
    event_marks_vacation,
    parse_time_str,
)

log = logging.getLogger("dac.scheduler")

STATE_IDLE = "idle"
STATE_SCHEDULED = "scheduled"
STATE_RINGING = "ringing"
STATE_STOPPED = "stopped"
STATE_DISMISSED = "dismissed"
STATE_VACATION = "vacation"

MODE_STANDARD = "standard"
MODE_DISMISSED = "dismissed"
MODE_VACATION = "vacation"

STATE_FILE = DATA_DIR / "state.json"
TICK_SECONDS = 10


def _now() -> datetime:
    """Current local time (timezone-aware)."""
    return datetime.now().astimezone()


class Coordinator:
    """Holds the alarm state and drives all timers."""

    def __init__(self) -> None:
        """Create the coordinator (call :meth:`start` to begin ticking)."""
        self._work_time: time | None = None
        self._work_time_day: date | None = None
        self._alarm_day: date | None = None
        self._alarm_time: time | None = None
        self._alarm_target: datetime | None = None
        self._state = STATE_IDLE
        self._state_day: date | None = None
        self._is_vacation = False
        self._vacation_override_day: date | None = None
        self._dismissed_days: set[date] = set()
        self._stopped_days: set[date] = set()
        self._test_target: datetime | None = None
        self._ring_started: datetime | None = None
        self._last_vacation_scan: date | None = None
        self._last_reminder_day: date | None = None
        self._last_watchdog: datetime | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()
        self.alexa = AlexaBridge(self)

    # ------------------------------------------------------------- lifecycle
    async def start(self) -> None:
        """Restore state, do a first schedule computation and start ticking."""
        await self.restore_state()
        await self.refresh_vacation()
        self.reschedule()
        self._task = asyncio.create_task(self._run())
        log.info("DAC scheduler started (state=%s target=%s)", self._state, self._alarm_target)

    async def stop(self) -> None:
        """Stop the tick task."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        """Tick loop: fire whatever is due (alarm, vacation scan, reminder)."""
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 – the loop must never die
                log.warning("DAC tick failed: %s", err)
            await asyncio.sleep(TICK_SECONDS)

    async def tick(self) -> None:
        """One scheduler iteration."""
        async with self._lock:
            now = _now()
            self._clear_stale_state(now)
            if self._is_vacation and self._state in (STATE_SCHEDULED, STATE_IDLE):
                self._set_state(STATE_VACATION)

            # Daily vacation scan shortly after midnight.
            if self._last_vacation_scan != now.date() and (now.hour, now.minute) >= (0, 1):
                self._last_vacation_scan = now.date()
                await self.refresh_vacation()

            # Reminder when no work time is set for tomorrow.
            if self._should_remind(now):
                self._last_reminder_day = now.date()
                await self._send_reminder(now)

            # Echo watchdog: make sure the device really holds the alarm.
            if self._last_watchdog is None or now - self._last_watchdog >= timedelta(minutes=30):
                self._last_watchdog = now
                await self.alexa.async_ensure_scheduled()

            # Test alarm due?
            if self._test_target is not None and now >= self._test_target:
                self._test_target = None
                await self._start_ringing(test=True)
                return

            # Real alarm due?
            if (
                self._state == STATE_SCHEDULED
                and self._alarm_target is not None
                and now >= self._alarm_target
            ):
                await self._start_ringing(test=False)
                return

            # While ringing, repeat the loop and honour the safety cap.
            if self._state == STATE_RINGING:
                if self._ring_expired(now):
                    log.info("DAC safety stop after %s min", self.max_ring_minutes)
                    await self.stop_alarm()
                    return
                if self._last_loop is None or now - self._last_loop >= timedelta(
                    minutes=self.loop_interval_minutes
                ):
                    self._last_loop = now
                    await self._fire_once()

    _last_loop: datetime | None = None

    # -------------------------------------------------------------- settings
    @property
    def default_alarm_time(self) -> time:
        """Configured fallback alarm time."""
        return parse_time_str(settings.get("default_alarm_time", "06:00"))

    @property
    def cutoff_time(self) -> time:
        """Time until which a manual work time may still arrive for tomorrow."""
        return parse_time_str(settings.get("reminder_time", "21:00"))

    @property
    def offset_minutes(self) -> int:
        """Minutes between alarm and work start."""
        try:
            return int(settings.get("offset_minutes", 60))
        except (TypeError, ValueError):
            return 60

    @property
    def loop_interval_minutes(self) -> int:
        """How often the ringing alarm repeats (1..60 minutes)."""
        try:
            value = int(settings.get("loop_interval_minutes", 5))
        except (TypeError, ValueError):
            value = 5
        return max(1, min(60, value))

    @property
    def max_ring_minutes(self) -> int:
        """Safety cap: end the alarm automatically after N minutes (0 = off)."""
        try:
            value = int(settings.get("max_ring_minutes", 60))
        except (TypeError, ValueError):
            value = 60
        return max(0, min(600, value))

    @property
    def turn_off_lights_on_stop(self) -> bool:
        """Whether the alarm lights go off when the alarm is stopped."""
        return settings.get_bool("turn_off_lights_on_stop", False)

    @property
    def reminder_via_alexa(self) -> bool:
        """Whether the daily reminder is also spoken on the Echo."""
        return settings.get_bool("reminder_via_alexa", True)

    @property
    def test_mode_active(self) -> bool:
        """True while a test alarm is pending or ringing."""
        return self._test_target is not None

    @property
    def current_mode(self) -> str:
        """Currently active mode (for the UI/select)."""
        today = _now().date()
        if self._vacation_override_day == today or self._is_vacation:
            return MODE_VACATION
        if today in self._dismissed_days:
            return MODE_DISMISSED
        return MODE_STANDARD

    # ---------------------------------------------------------------- state
    def _set_state(self, state: str) -> None:
        if state != self._state:
            self._state_day = _now().date()
        self._state = state

    def _clear_stale_state(self, now: datetime) -> bool:
        """Forget a sticky state left over from a past day."""
        if self._state in (STATE_IDLE, STATE_SCHEDULED, STATE_VACATION):
            return False
        if self._state_day is None or self._state_day >= now.date():
            return False
        log.info("DAC clearing stale '%s' state from %s", self._state, self._state_day)
        self._state = STATE_IDLE
        self._state_day = None
        self._last_loop = None
        return True

    def snapshot(self) -> dict[str, Any]:
        """Current state as a JSON-serialisable dict."""
        return {
            "state": self._state,
            "mode": self.current_mode,
            "work_time": self._work_time.strftime("%H:%M") if self._work_time else None,
            "work_time_day": self._work_time_day.isoformat() if self._work_time_day else None,
            "alarm_time": self._alarm_time.strftime("%H:%M") if self._alarm_time else None,
            "alarm_day": self._alarm_day.isoformat() if self._alarm_day else None,
            "alarm_target": self._alarm_target.isoformat() if self._alarm_target else None,
            "vacation": self._is_vacation,
            "offset_minutes": self.offset_minutes,
            "default_alarm_time": self.default_alarm_time.strftime("%H:%M"),
            "test_mode": self.test_mode_active,
            "test_target": self._test_target.isoformat() if self._test_target else None,
            "loop_interval_minutes": self.loop_interval_minutes,
            "last_placed": self.alexa.last_placed,
        }

    def desired_alarm_text(self) -> str | None:
        """The device alarm DAC currently wants on the Echo ('HH:MM' or None)."""
        if self._is_vacation or self._state == STATE_RINGING:
            return None
        if self._alarm_time is None or self._alarm_target is None:
            return None
        if self._alarm_day is not None and self._alarm_day in self._dismissed_days:
            return None
        target = self._alarm_target
        pre = self.alexa.pre_alarm_minutes
        if pre:
            shifted = target - timedelta(minutes=pre)
            if shifted.date() == target.date():
                target = shifted
        return target.strftime("%H:%M")

    # ----------------------------------------------------------- scheduling
    def reschedule(self) -> None:
        """Compute the next alarm and arm it."""
        if self._test_target is not None:
            return
        now = _now()
        self._clear_stale_state(now)
        if self._state == STATE_RINGING:
            return

        if self._is_vacation:
            self._set_state(STATE_VACATION)
            self._alarm_target = None
            self._sync_gate(False)
            return

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
            work_time = None

        if work_time is not None:
            work_day = self._work_time_day or now.date()
            shifted = compute_alarm_time(work_time, self.offset_minutes)
            candidate = datetime.combine(work_day, shifted, tzinfo=now.tzinfo)
            if shifted > work_time:
                candidate -= timedelta(days=1)
            if candidate <= now and work_day <= now.date():
                candidate += timedelta(days=1)
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
            self._sync_gate(False)
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
        self._sync_gate(True)
        log.debug(
            "DAC scheduled: day=%s work=%s target=%s state=%s",
            self._alarm_day,
            self._alarm_time,
            self._alarm_target,
            self._state,
        )

    def _sync_gate(self, on: bool) -> None:
        """Mirror the alarm state onto the wecker_aktiv gate."""
        if not self.alexa.enabled:
            return
        asyncio.create_task(self.alexa.async_set_gate(on))

    # --------------------------------------------------------- alarm runtime
    async def _start_ringing(self, test: bool) -> None:
        """Start the repeating wake loop."""
        if not test and (self._is_vacation or self._alarm_day in self._dismissed_days):
            self._set_state(STATE_VACATION if self._is_vacation else STATE_DISMISSED)
            return
        self._set_state(STATE_RINGING)
        self._ring_started = _now()
        self._last_loop = None
        await self.alexa.async_set_gate(True)
        await self._fire_once()
        log.info("DAC alarm ringing (%s)", "test" if test else "real")

    async def _fire_once(self) -> None:
        """One loop iteration: lights on, fresh Echo pre-alarm."""
        for light in settings.get_list("alarm_lights"):
            state = await ha.state(light)
            if state is not None and state.get("state") == "on":
                continue
            try:
                await ha.call_service("light", "turn_on", {"entity_id": light})
            except HomeAssistantError as err:
                log.warning("DAC could not turn on %s: %s", light, err)
        await self.alexa.async_pre_alarm()

    async def _turn_off_lights(self) -> None:
        """Switch the alarm lights back off."""
        for light in settings.get_list("alarm_lights"):
            state = await ha.state(light)
            if state is None or state.get("state") == "off":
                continue
            try:
                await ha.call_service("light", "turn_off", {"entity_id": light})
            except HomeAssistantError as err:
                log.warning("DAC could not turn off %s: %s", light, err)

    def _ring_expired(self, now: datetime) -> bool:
        """True when the safety cap (max ring minutes) has been reached."""
        limit = self.max_ring_minutes
        if not limit or self._ring_started is None:
            return False
        return now - self._ring_started >= timedelta(minutes=limit)

    async def _stop_loop(self, set_state: str | None = None) -> None:
        """Stop the wake loop and clear the device alarm."""
        self._last_loop = None
        self._test_target = None
        self._ring_started = None
        await self.alexa.async_clear_own()
        if set_state:
            self._set_state(set_state)

    # ------------------------------------------------------------- commands
    async def set_work_time(self, value: str, day: str | None = None) -> None:
        """Set the work start (and the day it belongs to)."""
        now = _now()
        work_time = parse_time_str(value)
        if day:
            work_day = date.fromisoformat(day)
        else:
            work_day = now.date() + (
                timedelta(days=1) if now.time() >= self.cutoff_time else timedelta(0)
            )
        self._work_time = work_time
        self._work_time_day = work_day
        self._dismissed_days.discard(work_day)
        self._stopped_days.discard(work_day)
        await self._stop_loop()
        self.reschedule()
        await self.save_state()
        await self.alexa.async_sync()

    async def clear_work_time(self) -> None:
        """Forget the manual work time (fall back to the default alarm)."""
        self._work_time = None
        self._work_time_day = None
        await self._stop_loop()
        self.reschedule()
        await self.save_state()
        await self.alexa.async_sync()

    async def start_test_alarm(self, minutes: int | None = None) -> None:
        """Ring a one-off test alarm in N minutes using the real wake loop."""
        default_minutes = settings.get("test_mode_minutes", 1)
        try:
            minutes_int = max(1, int(minutes if minutes is not None else default_minutes))
        except (TypeError, ValueError):
            minutes_int = 1
        await self._stop_loop()
        self._test_target = _now() + timedelta(minutes=minutes_int)
        self._set_state(STATE_SCHEDULED)
        log.info("DAC test alarm armed for %s", self._test_target)
        await self.save_state()

    async def cancel_test_alarm(self) -> None:
        """Cancel a pending test alarm (no effect once it rings)."""
        if self._test_target is None:
            return
        self._test_target = None
        if self._state == STATE_SCHEDULED:
            self._set_state(STATE_IDLE)
        self.reschedule()
        await self.save_state()

    async def stop_alarm(self) -> None:
        """Stop the looping alarm now."""
        was_ringing = self._state == STATE_RINGING
        was_test = self._test_target is not None
        self._test_target = None
        if was_ringing:
            if was_test:
                await self._stop_loop(set_state=STATE_IDLE)
            else:
                self._stopped_days.add(_now().date())
                await self._stop_loop(set_state=STATE_STOPPED)
            if self.turn_off_lights_on_stop:
                await self._turn_off_lights()
        else:
            await self._stop_loop()
        if was_ringing:
            await self.alexa.async_on_stop()
        else:
            await self.alexa.async_clear_own()
        self.reschedule()
        await self.save_state()

    async def dismiss_for_today(self, day: str | None = None) -> None:
        """Disable the alarm for today / the upcoming day."""
        now = _now()
        if day:
            target = date.fromisoformat(day)
        elif self._alarm_day is not None and self._alarm_target and now > self._alarm_target:
            target = self._alarm_day
        else:
            target = now.date()
        await self._dismiss_for(target)

    async def _dismiss_for(self, target: date) -> None:
        self._dismissed_days.add(target)
        await self._stop_loop(set_state=STATE_DISMISSED)
        self.reschedule()
        await self.save_state()
        await self.alexa.async_sync()

    async def set_mode(self, mode: str) -> None:
        """Set the alarm mode (standard / dismissed / vacation)."""
        today = _now().date()
        if mode == MODE_VACATION:
            self._vacation_override_day = today
            await self.refresh_vacation()
        elif mode == MODE_DISMISSED:
            self._vacation_override_day = None
            await self.refresh_vacation()
            await self._dismiss_for(today)
        else:
            self._vacation_override_day = None
            self._dismissed_days.discard(today)
            if self._state in (STATE_DISMISSED, STATE_STOPPED):
                self._set_state(STATE_IDLE)
            await self.refresh_vacation()
        self.reschedule()
        await self.save_state()
        await self.alexa.async_sync()

    async def set_alexa_alarm(self, value: str) -> None:
        """Place an explicit alarm on the Echo (panel button)."""
        await self.alexa.async_set_alarm(parse_time_str(value))

    # --------------------------------------------------------- vacation/scan
    async def refresh_vacation(self) -> None:
        """Check calendars for vacation/holiday events covering today."""
        today = _now().date()
        calendars = settings.get_list("vacation_calendars")
        vacation = False
        if calendars:
            keywords = [
                k.strip()
                for k in str(settings.get("vacation_keywords") or "").split(",")
                if k.strip()
            ]
            try:
                start = datetime.combine(today, time.min).astimezone().isoformat()
                end = datetime.combine(today + timedelta(days=1), time.min).astimezone().isoformat()
                result = await ha.call_service(
                    "calendar",
                    "get_events",
                    {"entity_id": calendars, "start_date_time": start, "end_date_time": end},
                    return_response=True,
                )
                events: list[dict[str, Any]] = []
                for response in (result or {}).values():
                    events.extend((response or {}).get("events") or [])
                vacation = any(event_marks_vacation(ev, today, keywords) for ev in events)
            except (HomeAssistantError, ValueError, AttributeError) as err:
                log.warning("DAC vacation check failed: %s", err)
        if self._vacation_override_day == today:
            vacation = True
        self._is_vacation = vacation
        if vacation and self._state in (STATE_SCHEDULED, STATE_IDLE):
            self._set_state(STATE_VACATION)
        self.reschedule()

    def _should_remind(self, now: datetime) -> bool:
        """True when the evening reminder is due."""
        if self._is_vacation:
            return False
        if self._last_reminder_day == now.date():
            return False
        remind_at = parse_time_str(settings.get("reminder_time", "21:00"))
        if now.time() < remind_at:
            return False
        tomorrow = now.date() + timedelta(days=1)
        if self._work_time_day in (now.date(), tomorrow):
            return False
        if self._state == STATE_RINGING:
            return False
        return bool(settings.get("notifier") or settings.get_bool("reminder_via_alexa", True))

    async def _send_reminder(self, now: datetime) -> None:
        """Send the reminder (notification and/or spoken on the Echo)."""
        self.reschedule()
        message = self._reminder_message()
        notifier = str(settings.get("notifier") or "")
        if notifier:
            domain, _, service = notifier.partition(".")
            if domain != "notify":
                domain, service = "notify", notifier
            try:
                await ha.call_service(domain, service, {"message": message})
            except HomeAssistantError as err:
                log.warning("DAC reminder via %s failed: %s", notifier, err)
        if self.reminder_via_alexa:
            await self.alexa.async_speak(_spoken_reminder(message))

    def _reminder_message(self) -> str:
        template = str(settings.get("reminder_text") or "")
        default_t = settings.get("default_alarm_time", "06:00")
        try:
            return template.format(alarm_time=default_t)
        except (KeyError, IndexError, ValueError):
            return template

    # ------------------------------------------------------------- volume
    def schedule_volume_restore(self, player: str, volume: float) -> None:
        """Restore the Echo volume shortly after the spoken reminder."""

        async def _restore() -> None:
            await asyncio.sleep(12)
            try:
                await ha.call_service(
                    "media_player", "volume_set", {"entity_id": player, "volume_level": volume}
                )
            except HomeAssistantError as err:
                log.debug("DAC could not restore the volume of %s: %s", player, err)

        asyncio.create_task(_restore())

    # ------------------------------------------------------------ persistence
    def _storage_payload(self) -> dict[str, Any]:
        return {
            "work_time": self._work_time.strftime("%H:%M:%S") if self._work_time else None,
            "work_time_day": self._work_time_day.isoformat() if self._work_time_day else None,
            "state": self._state,
            "alarm_day": self._alarm_day.isoformat() if self._alarm_day else None,
            "alarm_target": self._alarm_target.isoformat() if self._alarm_target else None,
            "dismissed": sorted(d.isoformat() for d in self._dismissed_days),
            "stopped": sorted(d.isoformat() for d in self._stopped_days),
            "last_placed": self.alexa.last_placed,
        }

    async def save_state(self) -> None:
        """Persist the mutable state (best effort)."""
        try:
            STATE_FILE.write_text(
                json.dumps(self._storage_payload(), ensure_ascii=False), encoding="utf-8"
            )
        except OSError as err:
            log.warning("DAC could not persist state: %s", err)

    async def restore_state(self) -> None:
        """Restore the persisted state after a restart."""
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        try:
            if data.get("work_time"):
                self._work_time = parse_time_str(data["work_time"])
                self._work_time_day = (
                    date.fromisoformat(data["work_time_day"]) if data.get("work_time_day") else None
                )
                if self._work_time_day and self._work_time_day < _now().date():
                    self._work_time = None
                    self._work_time_day = None
            today = _now().date()
            self._dismissed_days = {
                date.fromisoformat(d) for d in data.get("dismissed") or [] if d >= today.isoformat()
            }
            self._stopped_days = {
                date.fromisoformat(d) for d in data.get("stopped") or [] if d >= today.isoformat()
            }
            if data.get("alarm_day"):
                self._alarm_day = date.fromisoformat(data["alarm_day"])
            self.alexa.restore_last_placed(data.get("last_placed"))
            self._set_state(str(data.get("state") or STATE_IDLE))
        except (ValueError, TypeError) as err:
            log.warning("DAC could not restore state: %s", err)


def _spoken_reminder(message: str) -> str:
    """Turn the reminder text into a short, speakable sentence."""
    text = message.replace("⏰", " ").replace("DAC:", " ").replace("DAC", " ")
    return " ".join(text.split()) or "Bitte den Wecker für morgen stellen."


coordinator = Coordinator()
