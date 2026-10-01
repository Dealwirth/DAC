"""Option handling for DAC – shared by the config flow and the panel API.

The integration is configured entirely from the DAC sidebar panel, so the
config flow only creates an empty entry and this module owns the schema,
defaults and normalization of every editable option.
"""
from __future__ import annotations

from datetime import time
from typing import Any

import voluptuous as vol
from homeassistant.helpers.selector import (
    BooleanSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
    TimeSelector,
)

from .const import (
    CONF_ALARM_LIGHTS,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_DEFAULT_ALARM_TIME,
    CONF_LOOP_INTERVAL_MINUTES,
    CONF_NOTIFIER,
    CONF_OFFSET,
    CONF_PRE_ALARM_MINUTES,
    CONF_REMINDER_TEXT,
    CONF_REMINDER_TIME,
    CONF_STOP_WORD,
    CONF_TEST_MODE_MINUTES,
    CONF_VACATION_CALENDARS,
    CONF_VACATION_KEYWORDS,
    DEFAULT_ALARM_TIME,
    DEFAULT_ALEXA_ENABLED,
    DEFAULT_ALEXA_ENABLED_BOOLEAN,
    DEFAULT_ALEXA_TEXT_HELPER,
    DEFAULT_LOOP_INTERVAL_MINUTES,
    DEFAULT_OFFSET_MINUTES,
    DEFAULT_PRE_ALARM_MINUTES,
    DEFAULT_REMINDER_TEXT,
    DEFAULT_REMINDER_TIME,
    DEFAULT_STOP_WORD,
    DEFAULT_TEST_MODE_MINUTES,
    DEFAULT_VACATION_KEYWORDS,
    MAX_LOOP_INTERVAL_MINUTES,
    MAX_TEST_MODE_MINUTES,
    MIN_LOOP_INTERVAL_MINUTES,
)

TIME_KEYS = (CONF_DEFAULT_ALARM_TIME, CONF_REMINDER_TIME)
INT_KEYS = (CONF_OFFSET, CONF_PRE_ALARM_MINUTES, CONF_LOOP_INTERVAL_MINUTES, CONF_TEST_MODE_MINUTES)
BOOL_KEYS = (CONF_ALEXA_ENABLED,)
LIST_KEYS = (CONF_ALARM_LIGHTS, CONF_VACATION_CALENDARS)
STR_KEYS = (
    CONF_REMINDER_TEXT,
    CONF_NOTIFIER,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_STOP_WORD,
    CONF_VACATION_KEYWORDS,
)

# Every option the panel is allowed to write.
EDITABLE_KEYS: tuple[str, ...] = (
    *TIME_KEYS,
    *INT_KEYS,
    *BOOL_KEYS,
    *LIST_KEYS,
    *STR_KEYS,
)

# Fallbacks and hard bounds for the integer options.
_INT_DEFAULTS: dict[str, int] = {
    CONF_OFFSET: DEFAULT_OFFSET_MINUTES,
    CONF_PRE_ALARM_MINUTES: DEFAULT_PRE_ALARM_MINUTES,
    CONF_LOOP_INTERVAL_MINUTES: DEFAULT_LOOP_INTERVAL_MINUTES,
    CONF_TEST_MODE_MINUTES: DEFAULT_TEST_MODE_MINUTES,
}
_INT_BOUNDS: dict[str, tuple[int, int]] = {
    CONF_OFFSET: (0, 600),
    CONF_PRE_ALARM_MINUTES: (0, 30),
    CONF_LOOP_INTERVAL_MINUTES: (MIN_LOOP_INTERVAL_MINUTES, MAX_LOOP_INTERVAL_MINUTES),
    CONF_TEST_MODE_MINUTES: (1, MAX_TEST_MODE_MINUTES),
}


def default_options() -> dict[str, Any]:
    """The factory defaults for a fresh DAC entry."""
    return {
        CONF_DEFAULT_ALARM_TIME: DEFAULT_ALARM_TIME,
        CONF_OFFSET: DEFAULT_OFFSET_MINUTES,
        CONF_REMINDER_TIME: DEFAULT_REMINDER_TIME,
        CONF_REMINDER_TEXT: DEFAULT_REMINDER_TEXT,
        CONF_NOTIFIER: "notify.notify",
        CONF_ALARM_LIGHTS: [],
        CONF_VACATION_CALENDARS: [],
        CONF_ALEXA_ENABLED: DEFAULT_ALEXA_ENABLED,
        CONF_ALEXA_MEDIA_PLAYER: "",
        CONF_ALEXA_TEXT_HELPER: DEFAULT_ALEXA_TEXT_HELPER,
        CONF_ALEXA_ENABLED_BOOLEAN: DEFAULT_ALEXA_ENABLED_BOOLEAN,
        CONF_PRE_ALARM_MINUTES: DEFAULT_PRE_ALARM_MINUTES,
        CONF_LOOP_INTERVAL_MINUTES: DEFAULT_LOOP_INTERVAL_MINUTES,
        CONF_TEST_MODE_MINUTES: DEFAULT_TEST_MODE_MINUTES,
        CONF_STOP_WORD: DEFAULT_STOP_WORD,
        CONF_VACATION_KEYWORDS: ", ".join(DEFAULT_VACATION_KEYWORDS),
    }


def time_to_str(value: Any, fallback: str) -> str:
    """Normalize a time selector/panel value into a 'HH:MM:SS' string."""
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, str) and value:
        return value if value.count(":") == 2 else f"{value}:00"
    return fallback


def _as_list(value: Any) -> list[str]:
    """Accept a list, a single entity id or a comma separated string."""
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if item]
    return [str(value)]


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on", "ja")
    return bool(value)


def _as_int(value: Any, fallback: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return fallback


def coerce_options(data: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge incoming panel data over ``base`` and coerce every value.

    Unknown keys are ignored so a stale frontend can never inject junk into the
    config entry.
    """
    result = dict(base or {})
    for key, value in (data or {}).items():
        if key not in EDITABLE_KEYS:
            continue
        if key in TIME_KEYS:
            result[key] = time_to_str(value, result.get(key) or DEFAULT_ALARM_TIME)
        elif key in INT_KEYS:
            fallback = _INT_DEFAULTS.get(key, 0)
            value_int = _as_int(value, _as_int(result.get(key), fallback))
            low, high = _INT_BOUNDS.get(key, (None, None))
            if low is not None:
                value_int = max(low, value_int)
            if high is not None:
                value_int = min(high, value_int)
            result[key] = value_int
        elif key in BOOL_KEYS:
            result[key] = _as_bool(value)
        elif key in LIST_KEYS:
            result[key] = _as_list(value)
        elif key == CONF_VACATION_KEYWORDS:
            keywords = _as_list(value)
            result[key] = ", ".join(keywords)
        else:
            result[key] = "" if value is None else str(value)
    return result


def build_settings_schema(hass: Any, defaults: dict[str, Any]) -> vol.Schema:
    """Voluptuous schema for the HA-native config/options form."""
    notify_services = _notify_services(hass)
    return vol.Schema(
        {
            vol.Required(
                CONF_DEFAULT_ALARM_TIME,
                default=defaults.get(CONF_DEFAULT_ALARM_TIME, DEFAULT_ALARM_TIME),
            ): TimeSelector(),
            vol.Required(
                CONF_OFFSET,
                default=defaults.get(CONF_OFFSET, DEFAULT_OFFSET_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=0, max=600, step=5, unit_of_measurement="min", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                CONF_REMINDER_TIME,
                default=defaults.get(CONF_REMINDER_TIME, DEFAULT_REMINDER_TIME),
            ): TimeSelector(),
            vol.Required(
                CONF_REMINDER_TEXT,
                default=defaults.get(CONF_REMINDER_TEXT, DEFAULT_REMINDER_TEXT),
            ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
            vol.Required(
                CONF_NOTIFIER,
                default=defaults.get(CONF_NOTIFIER, "notify.notify"),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=notify_services,
                    mode=SelectSelectorMode.DROPDOWN,
                    custom_value=True,
                )
            ),
            vol.Optional(
                CONF_ALARM_LIGHTS,
                description={"suggested_value": defaults.get(CONF_ALARM_LIGHTS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="light", multiple=True)),
            vol.Optional(
                CONF_VACATION_CALENDARS,
                description={"suggested_value": defaults.get(CONF_VACATION_CALENDARS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="calendar", multiple=True)),
            vol.Optional(
                CONF_ALEXA_ENABLED,
                description={"suggested_value": defaults.get(CONF_ALEXA_ENABLED, False)},
            ): BooleanSelector(),
            vol.Optional(
                CONF_ALEXA_MEDIA_PLAYER,
                description={"suggested_value": defaults.get(CONF_ALEXA_MEDIA_PLAYER, "")},
            ): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=False)),
            vol.Optional(
                CONF_ALEXA_TEXT_HELPER,
                default=defaults.get(CONF_ALEXA_TEXT_HELPER, DEFAULT_ALEXA_TEXT_HELPER),
            ): EntitySelector(EntitySelectorConfig(domain="input_text")),
            vol.Optional(
                CONF_ALEXA_ENABLED_BOOLEAN,
                default=defaults.get(CONF_ALEXA_ENABLED_BOOLEAN, DEFAULT_ALEXA_ENABLED_BOOLEAN),
            ): EntitySelector(EntitySelectorConfig(domain="input_boolean")),
            vol.Optional(
                CONF_PRE_ALARM_MINUTES,
                default=defaults.get(CONF_PRE_ALARM_MINUTES, DEFAULT_PRE_ALARM_MINUTES),
            ): NumberSelector(NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)),
            vol.Required(
                CONF_LOOP_INTERVAL_MINUTES,
                default=defaults.get(
                    CONF_LOOP_INTERVAL_MINUTES, DEFAULT_LOOP_INTERVAL_MINUTES
                ),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_LOOP_INTERVAL_MINUTES,
                    max=MAX_LOOP_INTERVAL_MINUTES,
                    step=1,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Required(
                CONF_TEST_MODE_MINUTES,
                default=defaults.get(CONF_TEST_MODE_MINUTES, DEFAULT_TEST_MODE_MINUTES),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=1,
                    max=MAX_TEST_MODE_MINUTES,
                    step=1,
                    unit_of_measurement="min",
                    mode=NumberSelectorMode.BOX,
                )
            ),
            vol.Optional(
                CONF_STOP_WORD,
                default=defaults.get(CONF_STOP_WORD, DEFAULT_STOP_WORD),
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.TEXT)),
            vol.Optional(
                CONF_VACATION_KEYWORDS,
                default=defaults.get(CONF_VACATION_KEYWORDS, ", ".join(DEFAULT_VACATION_KEYWORDS)),
            ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
        }
    )


def _notify_services(hass: Any) -> list[str]:
    """Collect all available notify.* services for the selector."""
    services: list[str] = []
    try:
        all_services = hass.services.async_services()
    except AttributeError:
        return ["notify.notify"]
    for domain, services_map in all_services.items():
        if domain != "notify":
            continue
        for service in services_map:
            if not service.startswith("_"):
                services.append(f"notify.{service}")
    return sorted(services) or ["notify.notify"]


def vacation_keywords(options: dict[str, Any]) -> tuple[str, ...]:
    """The keywords that mark a calendar day as vacation/holiday."""
    raw = options.get(CONF_VACATION_KEYWORDS)
    if not raw:
        return DEFAULT_VACATION_KEYWORDS
    words = tuple(part.strip().lower() for part in str(raw).split(",") if part.strip())
    return words or DEFAULT_VACATION_KEYWORDS


__all__ = [
    "EDITABLE_KEYS",
    "build_settings_schema",
    "coerce_options",
    "default_options",
    "time_to_str",
    "vacation_keywords",
]
