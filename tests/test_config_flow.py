"""Tests for the DAC config and options flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dac.const import (
    CONF_DEFAULT_ALARM_TIME,
    CONF_OFFSET,
    CONF_VACATION_KEYWORDS,
    DOMAIN,
)
from custom_components.dac.settings import default_options


async def test_user_flow_creates_entry_without_questions(hass: HomeAssistant) -> None:
    """The user flow creates the entry immediately – no wizard questions."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_OFFSET] == default_options()[CONF_OFFSET]
    assert data[CONF_DEFAULT_ALARM_TIME] == default_options()[CONF_DEFAULT_ALARM_TIME]


async def test_duplicate_entry_aborts(hass: HomeAssistant) -> None:
    """A second entry is aborted because the unique id already exists."""
    await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.async_block_till_done()

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_values(
    hass: HomeAssistant, config_entry, options: dict
) -> None:
    """The HA-native options flow persists updated values (fallback to the panel)."""
    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "default_alarm_time": "07:30",
            "offset_minutes": 30,
            "reminder_time": "21:00",
            "reminder_text": "Neuer Text",
            "notifier": "notify.mobile_app_test",
            "alarm_lights": [],
            "vacation_calendars": [],
            CONF_VACATION_KEYWORDS: "urlaub, feiertag",
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY

    assert config_entry.options[CONF_OFFSET] == 30
    assert config_entry.options["notifier"] == "notify.mobile_app_test"
    assert config_entry.options[CONF_VACATION_KEYWORDS] == "urlaub, feiertag"


async def test_entry_from_real_flow_is_usable(hass: HomeAssistant) -> None:
    """The entry created by the (question-free) user flow loads and works."""
    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        await hass.async_block_till_done()

    entry = result["result"]
    coordinator = hass.data[DOMAIN][entry.entry_id]
    # Options come from entry.data – the coordinator must read them too.
    assert coordinator.offset_minutes == default_options()[CONF_OFFSET]
    assert coordinator.default_alarm_time.strftime("%H:%M") == "06:00"
