"""Configuration for the DAC app.

Options come from the Supervisor (``/data/options.json``). They are merged
with the values stored in ``/data/settings.json`` so the UI can change nearly
every setting at runtime without a restart of the app.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("dac.config")

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUPERVISOR_URL = "http://supervisor"
DATA_DIR = Path(os.environ.get("DAC_DATA", "/data"))
OPTIONS_FILE = Path("/data/options.json")
SETTINGS_FILE = DATA_DIR / "settings.json"

_lock = threading.RLock()

DEFAULTS: dict[str, Any] = {
    "ha_url": "http://supervisor/core",
    "ha_token": "",
    "default_alarm_time": "06:00",
    "offset_minutes": 60,
    "loop_interval_minutes": 5,
    "max_ring_minutes": 60,
    "test_mode_minutes": 1,
    "reminder_time": "21:00",
    "reminder_text": (
        "⏰ DAC: Für morgen ist noch keine Arbeitszeit gesetzt – bitte den Wecker "
        "stellen. Sonst klingelt der Standard-Wecker um {alarm_time} Uhr."
    ),
    "notifier": "",
    "alarm_lights": [],
    "vacation_calendars": [],
    "vacation_keywords": (
        "urlaub, urlaubstag, feiertag, ferien, freizeitausgleich, vacation, holiday"
    ),
    "turn_off_lights_on_stop": False,
    "alexa_enabled": True,
    "alexa_media_player": "",
    "alexa_text_helper": "input_text.gestellter_alexa_wecker",
    "alexa_enabled_boolean": "input_boolean.wecker_aktiv",
    "pre_alarm_minutes": 2,
    "alexa_alarm_name": "",
    "stop_word": "Wecker aus",
    "reminder_via_alexa": True,
    "reminder_alexa_volume": 15,
    "mqtt_enabled": False,
    "mqtt_host": "core-mosquitto",
    "mqtt_port": 1883,
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_discovery_prefix": "homeassistant",
    "log_level": "info",
}

# Options the UI is allowed to change (everything except the HA connection).
EDITABLE = {
    "default_alarm_time",
    "offset_minutes",
    "loop_interval_minutes",
    "max_ring_minutes",
    "test_mode_minutes",
    "reminder_time",
    "reminder_text",
    "notifier",
    "alarm_lights",
    "vacation_calendars",
    "vacation_keywords",
    "turn_off_lights_on_stop",
    "alexa_enabled",
    "alexa_media_player",
    "alexa_text_helper",
    "alexa_enabled_boolean",
    "pre_alarm_minutes",
    "alexa_alarm_name",
    "stop_word",
    "reminder_via_alexa",
    "reminder_alexa_volume",
    "mqtt_enabled",
    "mqtt_host",
    "mqtt_port",
    "mqtt_username",
    "mqtt_password",
    "mqtt_discovery_prefix",
    "log_level",
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class Settings:
    """Runtime settings merged from Supervisor options and the saved file."""

    def __init__(self) -> None:
        """Load the initial settings."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = dict(DEFAULTS)
        self._data.update(_read_json(OPTIONS_FILE))
        self._data.update(_read_json(SETTINGS_FILE))
        self._normalize()
        log.info("DAC settings loaded (%s)", DATA_DIR)

    def _normalize(self) -> None:
        """Coerce types and drop empty optional values."""
        for key in ("alarm_lights", "vacation_calendars"):
            value = self._data.get(key)
            if value is None:
                self._data[key] = []
            elif isinstance(value, str):
                self._data[key] = [v.strip() for v in value.split(",") if v.strip()]
            elif isinstance(value, list):
                self._data[key] = [str(v).strip() for v in value if str(v).strip()]
            else:
                self._data[key] = []
        for key, default in (("offset_minutes", 60), ("loop_interval_minutes", 5)):
            try:
                self._data[key] = int(self._data.get(key, default))
            except (TypeError, ValueError):
                self._data[key] = default

    def get(self, key: str, default: Any = None) -> Any:
        """Read a setting (falls back to the given default)."""
        with _lock:
            return self._data.get(key, default)

    def get_int(self, key: str, default: int) -> int:
        """Read an integer setting."""
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Read a boolean setting."""
        value = self.get(key, default)
        if isinstance(value, str):
            return value.strip().lower() in ("1", "true", "yes", "on", "ja")
        return bool(value)

    def get_list(self, key: str) -> list[str]:
        """Read a list setting."""
        value = self.get(key, [])
        return list(value) if isinstance(value, list) else []

    def all(self) -> dict[str, Any]:
        """A copy of all settings (passwords masked)."""
        with _lock:
            data = dict(self._data)
        if data.get("ha_token"):
            data["ha_token"] = "********"
        if data.get("mqtt_password"):
            data["mqtt_password"] = "********"
        return data

    def update(self, changes: dict[str, Any]) -> dict[str, Any]:
        """Apply editable changes and persist them."""
        with _lock:
            for key, value in changes.items():
                if key in EDITABLE:
                    self._data[key] = value
            self._normalize()
            self._save()
            return dict(self._data)

    def _save(self) -> None:
        try:
            SETTINGS_FILE.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as err:
            log.warning("DAC could not save settings: %s", err)


settings = Settings()
