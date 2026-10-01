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
    CONF_ALARM_VOLUME,
    CONF_ALEXA_COMMAND_TYPE,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_DEFAULT_ALARM_TIME,
    CONF_MEDIA_PLAYERS,
    CONF_NOTIFIER,
    CONF_OFFSET,
    CONF_PRE_ALARM_MINUTES,
    CONF_REMINDER_TEXT,
    CONF_REMINDER_TIME,
    CONF_VACATION_CALENDARS,
    CONF_VACATION_KEYWORDS,
    CONF_WAKE_TEXT,
    ALEXA_COMMAND_TYPE_CUSTOM,
    ALEXA_COMMAND_TYPES,
    DEFAULT_ALARM_TIME,
    DEFAULT_ALARM_VOLUME,
    DEFAULT_ALEXA_COMMAND_TYPE,
    DEFAULT_ALEXA_ENABLED,
    DEFAULT_ALEXA_ENABLED_BOOLEAN,
    DEFAULT_ALEXA_TEXT_HELPER,
    DEFAULT_OFFSET_MINUTES,
    DEFAULT_PRE_ALARM_MINUTES,
    DEFAULT_REMINDER_TEXT,
    DEFAULT_REMINDER_TIME,
    DEFAULT_VACATION_KEYWORDS,
    DEFAULT_WAKE_TEXT,
)

TIME_KEYS = (CONF_DEFAULT_ALARM_TIME, CONF_REMINDER_TIME)
INT_KEYS = (CONF_OFFSET, CONF_PRE_ALARM_MINUTES)
FLOAT_KEYS = (CONF_ALARM_VOLUME,)
BOOL_KEYS = (CONF_ALEXA_ENABLED,)
LIST_KEYS = (CONF_ALARM_LIGHTS, CONF_MEDIA_PLAYERS, CONF_VACATION_CALENDARS)
STR_KEYS = (
    CONF_REMINDER_TEXT,
    CONF_NOTIFIER,
    CONF_ALEXA_MEDIA_PLAYER,
    CONF_ALEXA_TEXT_HELPER,
    CONF_ALEXA_ENABLED_BOOLEAN,
    CONF_ALEXA_COMMAND_TYPE,
    CONF_WAKE_TEXT,
    CONF_VACATION_KEYWORDS,
)

# Every option the panel is allowed to write.
EDITABLE_KEYS: tuple[str, ...] = (
    *TIME_KEYS,
    *INT_KEYS,
    *FLOAT_KEYS,
    *BOOL_KEYS,
    *LIST_KEYS,
    *STR_KEYS,
)


def default_options() -> dict[str, Any]:
    """The factory defaults for a fresh DAC entry."""
    return {
        CONF_DEFAULT_ALARM_TIME: DEFAULT_ALARM_TIME,
        CONF_OFFSET: DEFAULT_OFFSET_MINUTES,
        CONF_REMINDER_TIME: DEFAULT_REMINDER_TIME,
        CONF_REMINDER_TEXT: DEFAULT_REMINDER_TEXT,
        CONF_NOTIFIER: "notify.notify",
        CONF_ALARM_LIGHTS: [],
        CONF_MEDIA_PLAYERS: [],
        CONF_VACATION_CALENDARS: [],
        CONF_ALARM_VOLUME: DEFAULT_ALARM_VOLUME,
        CONF_ALEXA_ENABLED: DEFAULT_ALEXA_ENABLED,
        CONF_ALEXA_MEDIA_PLAYER: "",
        CONF_ALEXA_TEXT_HELPER: DEFAULT_ALEXA_TEXT_HELPER,
        CONF_ALEXA_ENABLED_BOOLEAN: DEFAULT_ALEXA_ENABLED_BOOLEAN,
        CONF_ALEXA_COMMAND_TYPE: DEFAULT_ALEXA_COMMAND_TYPE,
        CONF_PRE_ALARM_MINUTES: DEFAULT_PRE_ALARM_MINUTES,
        CONF_VACATION_KEYWORDS: ", ".join(DEFAULT_VACATION_KEYWORDS),
        CONF_WAKE_TEXT: DEFAULT_WAKE_TEXT,
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


def _as_float(value: Any, fallback: float) -> float:
    try:
        return float(value)
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
            fallback = DEFAULT_OFFSET_MINUTES if key == CONF_OFFSET else DEFAULT_PRE_ALARM_MINUTES
            result[key] = _as_int(value, _as_int(result.get(key), fallback))
        elif key in FLOAT_KEYS:
            result[key] = max(
                0.0,
                min(1.0, _as_float(value, _as_float(result.get(key), DEFAULT_ALARM_VOLUME))),
            )
        elif key in BOOL_KEYS:
            result[key] = _as_bool(value)
        elif key in LIST_KEYS:
            result[key] = _as_list(value)
        elif key == CONF_VACATION_KEYWORDS:
            keywords = _as_list(value)
            result[key] = ", ".join(keywords)
        elif key == CONF_ALEXA_COMMAND_TYPE:
            result[key] = (
                value if value in ALEXA_COMMAND_TYPES else ALEXA_COMMAND_TYPE_CUSTOM
            )
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
                CONF_MEDIA_PLAYERS,
                description={"suggested_value": defaults.get(CONF_MEDIA_PLAYERS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="media_player", multiple=True)),
            vol.Optional(
                CONF_VACATION_CALENDARS,
                description={"suggested_value": defaults.get(CONF_VACATION_CALENDARS, [])},
            ): EntitySelector(EntitySelectorConfig(domain="calendar", multiple=True)),
            vol.Required(
                CONF_ALARM_VOLUME,
                default=defaults.get(CONF_ALARM_VOLUME, DEFAULT_ALARM_VOLUME),
            ): NumberSelector(
                NumberSelectorConfig(min=0, max=1, step=0.05, mode=NumberSelectorMode.SLIDER)
            ),
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
                CONF_ALEXA_COMMAND_TYPE,
                default=defaults.get(CONF_ALEXA_COMMAND_TYPE, DEFAULT_ALEXA_COMMAND_TYPE),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(ALEXA_COMMAND_TYPES),
                    mode=SelectSelectorMode.DROPDOWN,
                    translation_key="alexa_command_type",
                )
            ),
            vol.Optional(
                CONF_PRE_ALARM_MINUTES,
                default=defaults.get(CONF_PRE_ALARM_MINUTES, DEFAULT_PRE_ALARM_MINUTES),
            ): NumberSelector(NumberSelectorConfig(min=0, max=30, step=1, mode=NumberSelectorMode.BOX)),
            vol.Optional(
                CONF_VACATION_KEYWORDS,
                default=defaults.get(CONF_VACATION_KEYWORDS, ", ".join(DEFAULT_VACATION_KEYWORDS)),
            ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
            vol.Optional(
                CONF_WAKE_TEXT,
                default=defaults.get(CONF_WAKE_TEXT, DEFAULT_WAKE_TEXT),
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
