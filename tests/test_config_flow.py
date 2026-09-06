"""Tests for the DAC config and options flow."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dac.const import DOMAIN


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user flow accepts the form and creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "default_alarm_time": "06:00",
            "offset_minutes": 45,
            "reminder_time": "20:30",
            "reminder_text": "Denk an die Arbeitszeit!",
            "notifier": "notify.notify",
            "alarm_lights": [],
            "media_players": [],
            "vacation_calendars": [],
            "alarm_volume": 0.5,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["offset_minutes"] == 45
    assert data["notifier"] == "notify.notify"
    assert data["default_alarm_time"] in ("06:00", "06:00:00")


async def test_duplicate_entry_aborts(hass: HomeAssistant) -> None:
    """A second entry with the same unique id is aborted."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "default_alarm_time": "06:00",
            "offset_minutes": 60,
            "reminder_time": "20:30",
            "reminder_text": "text",
            "notifier": "notify.notify",
            "alarm_volume": 0.5,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY

    # Try again with the same unique id
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "default_alarm_time": "07:00",
            "offset_minutes": 30,
            "reminder_time": "21:00",
            "reminder_text": "text",
            "notifier": "notify.notify",
            "alarm_volume": 0.5,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_updates_values(
    hass: HomeAssistant, config_entry, options: dict
) -> None:
    """The options flow persists updated values and reloads the entry."""
    from unittest.mock import AsyncMock, patch

    with patch("custom_components.dac.async_register_panel", new=AsyncMock()):
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
            "media_players": [],
            "vacation_calendars": [],
            "alarm_volume": 0.8,
        },
    )
    await hass.async_block_till_done()
    assert result["type"] == FlowResultType.CREATE_ENTRY

    assert config_entry.options["offset_minutes"] == 30
    assert config_entry.options["notifier"] == "notify.mobile_app_test"
