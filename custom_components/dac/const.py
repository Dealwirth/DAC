"""Constants for the DAC – Dynamic Alarm Clock integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "dac"
MANUFACTURER: Final = "Dealwirth"

# --- Services -------------------------------------------------------------
SERVICE_SET_WORK_TIME: Final = "set_work_time"
SERVICE_STOP_ALARM: Final = "stop_alarm"
SERVICE_DISMISS_FOR_TODAY: Final = "dismiss_for_today"
SERVICE_START_TEST_ALARM: Final = "start_test_alarm"
SERVICE_CANCEL_TEST_ALARM: Final = "cancel_test_alarm"

# --- Config / option keys --------------------------------------------------
CONF_DEFAULT_ALARM_TIME: Final = "default_alarm_time"          # "06:00"
CONF_OFFSET: Final = "offset_minutes"                          # minutes BEFORE work start
CONF_REMINDER_TIME: Final = "reminder_time"                    # "20:30"
CONF_REMINDER_TEXT: Final = "reminder_text"
CONF_NOTIFIER: Final = "notifier"                              # notify.xxx service
CONF_ALARM_LIGHTS: Final = "alarm_lights"                      # list of light entities
CONF_VACATION_CALENDARS: Final = "vacation_calendars"          # optional external calendar entities
CONF_VACATION_KEYWORDS: Final = "vacation_keywords"            # words that mark a day as off
CONF_LOOP_INTERVAL_MINUTES: Final = "loop_interval_minutes"    # how often the alarm repeats
CONF_TEST_MODE_MINUTES: Final = "test_mode_minutes"            # test alarm rings in N minutes
CONF_STOP_WORD: Final = "stop_word"                            # alarm name that stops DAC via Alexa

# --- Defaults --------------------------------------------------------------
DEFAULT_NAME: Final = "DAC"
DEVICE_NAME: Final = "DAC Wecker"
DEFAULT_ALARM_TIME: Final = "06:00"
DEFAULT_OFFSET_MINUTES: Final = 60
DEFAULT_REMINDER_TIME: Final = "20:30"
DEFAULT_REMINDER_TEXT: Final = (
    "⏰ DAC: Für morgen wurde noch keine Arbeitszeit gesetzt. "
    "Der Standard-Wecker ({alarm_time}) greift, wenn nichts gesetzt wird."
)
DEFAULT_VACATION_KEYWORDS: Final = (
    "urlaub",
    "urlaubstag",
    "feiertag",
    "ferien",
    "freizeitausgleich",
    "vacation",
    "holiday",
)
DEFAULT_LOOP_INTERVAL_MINUTES: Final = 5
DEFAULT_TEST_MODE_MINUTES: Final = 1
DEFAULT_STOP_WORD: Final = "Wecker aus"
DEFAULT_VACATION_SCAN_TIME: Final = "00:01"

# Loop interval bounds (a too-short interval would spam the Echo).
MIN_LOOP_INTERVAL_MINUTES: Final = 1
MAX_LOOP_INTERVAL_MINUTES: Final = 60
MAX_TEST_MODE_MINUTES: Final = 120

# --- Internal states (sensor attribute + diagnostics) ----------------------
STATE_IDLE: Final = "idle"
STATE_SCHEDULED: Final = "scheduled"
STATE_RINGING: Final = "ringing"
STATE_STOPPED: Final = "stopped"
STATE_DISMISSED: Final = "dismissed"
STATE_VACATION: Final = "vacation"

# --- Select modes ----------------------------------------------------------
MODE_STANDARD: Final = "standard"
MODE_DISMISSED: Final = "dismissed"
MODE_VACATION: Final = "vacation"

# --- Entities / platform setup --------------------------------------------
PLATFORMS: Final = ["sensor", "select", "time", "calendar"]
STORAGE_VERSION: Final = 1

# --- Service field names ---------------------------------------------------
ATTR_TIME: Final = "time"
ATTR_DAY: Final = "day"
ATTR_CLEAR: Final = "clear"

# --- Alexa device-alarm integration -----------------------------------------
# DAC places a *real* alarm on the Echo device (text command to Alexa), just
# like the YAML automation. The Echo then rings even if Home Assistant is
# unavailable.
CONF_ALEXA_ENABLED: Final = "alexa_enabled"            # bool, default False
CONF_ALEXA_MEDIA_PLAYER: Final = "alexa_media_player"   # alexa_media entity
CONF_ALEXA_TEXT_HELPER: Final = "alexa_text_helper"     # input_text with the set alarm
CONF_ALEXA_ENABLED_BOOLEAN: Final = "alexa_enabled_boolean"  # input_boolean gate
CONF_PRE_ALARM_MINUTES: Final = "pre_alarm_minutes"     # device alarm rings N min before

DEFAULT_ALEXA_ENABLED: Final = False
DEFAULT_ALEXA_TEXT_HELPER: Final = "input_text.gestellter_alexa_wecker"
DEFAULT_ALEXA_ENABLED_BOOLEAN: Final = "input_boolean.wecker_aktiv"
DEFAULT_PRE_ALARM_MINUTES: Final = 2

# Text commands for Alexa – the AM/PM suffix ("morgens"/"abends") prevents
# Alexa from asking back for the time of day.
ALEXA_SET_TEXT: Final = "stelle einen Wecker auf {time} Uhr {tod}"
ALEXA_CLEAR_TEXT: Final = "lösche den Wecker um {time} Uhr"

# DAC names every alarm it places with the stop word. An Alexa routine whose
# trigger is "an alarm with this name rings" can then call dac.stop_alarm, so
# stopping by voice needs no custom skill and no cloud hook.
ALEXA_STOP_ALARM_TEXT: Final = "stelle einen Wecker auf {time} Uhr {tod} namens {label}"
ALEXA_ROUTINE_NAME: Final = "DAC Stopp"

# --- Services (Alexa) -------------------------------------------------------
SERVICE_SET_ALEXA_ALARM: Final = "set_alexa_alarm"
SERVICE_CLEAR_ALEXA_ALARM: Final = "clear_alexa_alarm"

# --- Sidebar panel ----------------------------------------------------------
# Ein einziger Sidebar-Eintrag „DAC“; die früheren Seiten (Steuerung,
# Einstellungen, Kalender, Hilfe) sind jetzt Tabs innerhalb dieses Dashboards.
PANEL_URL_PATH: Final = "dac"
PANEL_ELEMENT: Final = "dac-panel"
PANEL_MODULE_PATH: Final = "/dac/static/dac-panel.js"
PANEL_TITLE: Final = "DAC"

# Entity search: the API offers every entity as one flat searchable list; the
# panel filters it per field by domain. Only noisy/internal domains are skipped.
ENTITY_SEARCH_EXCLUDE_DOMAINS: Final = (
    "zone",
    "sun",
    "persistent_notification",
    "update",
    "tts",
    "stt",
    "conversation",
    "assist_satellite",
    "todo",
    "tag",
)
