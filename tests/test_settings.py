"""Tests for the DAC option handling shared by the panel and the config flow."""
from __future__ import annotations

from datetime import time

from homeassistant.core import HomeAssistant

from custom_components.dac.const import (
    CONF_ALARM_VOLUME,
    CONF_ALEXA_COMMAND_TYPE,
    CONF_ALEXA_ENABLED,
    CONF_DEFAULT_ALARM_TIME,
    CONF_OFFSET,
    CONF_VACATION_KEYWORDS,
    CONF_WAKE_TEXT,
    DEFAULT_VACATION_KEYWORDS,
)
from custom_components.dac.settings import (
    EDITABLE_KEYS,
    build_settings_schema,
    coerce_options,
    default_options,
    vacation_keywords,
)


def test_defaults_cover_every_editable_key() -> None:
    defaults = default_options()
    assert set(EDITABLE_KEYS) <= set(defaults)


def test_coerce_options_normalizes_everything() -> None:
    result = coerce_options(
        {
            CONF_DEFAULT_ALARM_TIME: time(7, 15),
            CONF_OFFSET: "45",
            CONF_ALARM_VOLUME: "1.7",
            CONF_ALEXA_ENABLED: "ja",
            "alarm_lights": "light.a, light.b",
            "media_players": ["media_player.echo"],
            CONF_VACATION_KEYWORDS: "urlaub, brückentag",
            CONF_WAKE_TEXT: "Aufstehen!",
        },
        default_options(),
    )
    assert result[CONF_DEFAULT_ALARM_TIME] == "07:15:00"
    assert result[CONF_OFFSET] == 45
    assert result[CONF_ALARM_VOLUME] == 1.0  # clamped
    assert result[CONF_ALEXA_ENABLED] is True
    assert result["alarm_lights"] == ["light.a", "light.b"]
    assert result["media_players"] == ["media_player.echo"]
    assert result[CONF_VACATION_KEYWORDS] == "urlaub, brückentag"
    assert result[CONF_WAKE_TEXT] == "Aufstehen!"


def test_coerce_options_normalizes_command_type() -> None:
    """The Alexa command type is restricted to the known values."""
    assert coerce_options({CONF_ALEXA_COMMAND_TYPE: "tts"}, default_options())[
        CONF_ALEXA_COMMAND_TYPE
    ] == "tts"
    assert coerce_options({CONF_ALEXA_COMMAND_TYPE: "bogus"}, default_options())[
        CONF_ALEXA_COMMAND_TYPE
    ] == "custom"


def test_coerce_options_ignores_unknown_keys_and_keeps_base() -> None:
    base = default_options()
    base[CONF_OFFSET] = 20
    result = coerce_options({"junk": 1, CONF_WAKE_TEXT: None}, base)
    assert "junk" not in result
    assert result[CONF_OFFSET] == 20
    assert result[CONF_WAKE_TEXT] == ""


def test_vacation_keywords_fallback_and_parsing() -> None:
    assert vacation_keywords({}) == DEFAULT_VACATION_KEYWORDS
    assert vacation_keywords({CONF_VACATION_KEYWORDS: "  "}) == DEFAULT_VACATION_KEYWORDS
    assert vacation_keywords({CONF_VACATION_KEYWORDS: "Urlaub, Feiertag"}) == (
        "urlaub",
        "feiertag",
    )


def test_build_settings_schema_covers_all_editable_keys(hass: HomeAssistant) -> None:
    """The HA-native form offers exactly the editable options."""
    schema = build_settings_schema(hass, default_options())
    keys = {str(key) for key in schema.schema}
    assert keys == set(EDITABLE_KEYS)
