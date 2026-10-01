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
CONF_NOTIFIER: Final = "notifier"                              # notify.xxx entity
CONF_ALARM_LIGHTS: Final = "alarm_lights"                      # list of light entities
CONF_MEDIA_PLAYERS: Final = "media_players"                    # list of media_player entities
CONF_VACATION_CALENDARS: Final = "vacation_calendars"          # optional external calendar entities
CONF_ALARM_VOLUME: Final = "alarm_volume"                      # 0.0 .. 1.0
CONF_VACATION_KEYWORDS: Final = "vacation_keywords"            # words that mark a day as off
CONF_WAKE_TEXT: Final = "wake_text"                            # spoken/announced wake text
CONF_ALEXA_COMMAND_TYPE: Final = "alexa_command_type"          # "custom" (text command) or "tts"
CONF_LOOP_INTERVAL_MINUTES: Final = "loop_interval_minutes"    # how often the alarm repeats
CONF_TEST_MODE_MINUTES: Final = "test_mode_minutes"            # test alarm rings in N minutes
CONF_STOP_WORD: Final = "stop_word"                            # word that stops the alarm via Alexa

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
DEFAULT_ALARM_VOLUME: Final = 0.5
DEFAULT_VACATION_KEYWORDS: Final = (
    "urlaub",
    "urlaubstag",
    "feiertag",
    "ferien",
    "freizeitausgleich",
    "vacation",
    "holiday",
)
DEFAULT_WAKE_TEXT: Final = "Guten Morgen! Es ist Zeit aufzustehen."
DEFAULT_LOOP_INTERVAL_MINUTES: Final = 5
DEFAULT_TEST_MODE_MINUTES: Final = 1
DEFAULT_STOP_WORD: Final = "Wecker aus"
DEFAULT_VACATION_SCAN_TIME: Final = "00:01"

# Loop interval bounds (a too-short interval would spam the Echo/players).
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
# Optional: DAC legt zusätzlich einen "echten" Wecker auf dem Echo-Gerät an
# (Text-Befehl an Alexa). Dadurch klingelt der Wecker auch, wenn Home
# Assistant gerade nicht erreichbar ist.
CONF_ALEXA_ENABLED: Final = "alexa_enabled"            # bool, default False
CONF_ALEXA_MEDIA_PLAYER: Final = "alexa_media_player"   # alexa_media entity
CONF_ALEXA_TEXT_HELPER: Final = "alexa_text_helper"     # input_text with the set alarm
CONF_ALEXA_ENABLED_BOOLEAN: Final = "alexa_enabled_boolean"  # input_boolean gate
CONF_PRE_ALARM_MINUTES: Final = "pre_alarm_minutes"     # device alarm rings N min before

DEFAULT_ALEXA_ENABLED: Final = False
DEFAULT_ALEXA_TEXT_HELPER: Final = "input_text.gestellter_alexa_wecker"
DEFAULT_ALEXA_ENABLED_BOOLEAN: Final = "input_boolean.wecker_aktiv"
DEFAULT_PRE_ALARM_MINUTES: Final = 2

# Alexa understands the command best when it is sent as a plain text command
# (media_content_type "custom", like the classic YAML automation). "tts" is
# kept as a fallback for setups where "custom" is not available.
ALEXA_COMMAND_TYPE_CUSTOM: Final = "custom"
ALEXA_COMMAND_TYPE_TTS: Final = "tts"
ALEXA_COMMAND_TYPES: Final = (ALEXA_COMMAND_TYPE_CUSTOM, ALEXA_COMMAND_TYPE_TTS)
DEFAULT_ALEXA_COMMAND_TYPE: Final = ALEXA_COMMAND_TYPE_CUSTOM

# Text commands for Alexa – the AM/PM suffix ("morgens"/"abends") prevents
# Alexa from asking back for the time of day.
ALEXA_SET_TEXT: Final = "stelle einen Wecker auf {time} Uhr {tod}"
ALEXA_CLEAR_TEXT: Final = "lösche den Wecker um {time} Uhr"

# Optional "stop the alarm by voice": DAC sets an Alexa routine trigger phrase
# as a *device alarm label*. When that labelled alarm rings, the Alexa app can
# run a routine ("DAC Stopp") that calls dac.stop_alarm – no custom skill,
# no cloud hook, works with the official Alexa app only.
ALEXA_STOP_ALARM_TEXT: Final = "stelle einen Wecker auf {time} Uhr {tod} namens {label}"
ALEXA_ROUTINE_NAME: Final = "DAC Stopp"

# --- Services (Alexa) -------------------------------------------------------
SERVICE_SET_ALEXA_ALARM: Final = "set_alexa_alarm"
SERVICE_CLEAR_ALEXA_ALARM: Final = "clear_alexa_alarm"

# --- Sidebar panel ----------------------------------------------------------
PANEL_URL_PATH: Final = "dac"
PANEL_ELEMENT: Final = "dac-panel"
PANEL_MODULE_PATH: Final = "/dac/static/dac-panel.js"
PANEL_TITLE: Final = "DAC"
