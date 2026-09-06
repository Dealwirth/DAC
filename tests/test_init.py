"""End-to-end tests: config entry setup, services and entity creation."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dac.const import DOMAIN

from tests.conftest import FakeCall


async def test_setup_creates_entities_and_services(
    hass: HomeAssistant, config_entry: MockConfigEntry, options: dict
) -> None:
    """A config entry sets up the coordinator, entities and services."""
    with patch("custom_components.dac.async_register_panel", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED

    # Coordinator registered
    assert config_entry.entry_id in hass.data[DOMAIN]

    # Entities exist (entity_id derived from the explicit entity names)
    assert hass.states.get("sensor.dac_next_alarm") is not None
    assert hass.states.get("select.dac_modus") is not None
    assert hass.states.get("time.dac_arbeitsbeginn") is not None
    assert hass.states.get("calendar.dac_urlaubskalender") is not None

    # Services registered
    assert hass.services.has_service(DOMAIN, "set_work_time")
    assert hass.services.has_service(DOMAIN, "stop_alarm")
    assert hass.services.has_service(DOMAIN, "dismiss_for_today")

    # Unload removes services and coordinator
    await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED
    assert not hass.services.has_service(DOMAIN, "set_work_time")
    assert config_entry.entry_id not in hass.data[DOMAIN]


async def test_set_work_time_service_updates_sensor(
    hass: HomeAssistant, config_entry: MockConfigEntry, options: dict
) -> None:
    """Calling dac.set_work_time schedules the alarm on the sensor."""
    with patch("custom_components.dac.async_register_panel", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN, "set_work_time", {"time": "15:00"}, blocking=True
    )
    await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    assert coordinator._work_time.strftime("%H:%M") == "15:00"
    assert coordinator._state == "scheduled"

    sensor = hass.states.get("sensor.dac_next_alarm")
    assert sensor is not None
    assert sensor.attributes["state"] == "scheduled"


async def test_stop_and_dismiss_services(
    hass: HomeAssistant, config_entry: MockConfigEntry, options: dict
) -> None:
    """stop_alarm and dismiss_for_today run without errors."""
    with patch("custom_components.dac.async_register_panel", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.async_set_work_time(FakeCall({"time": "23:59"}))

    await hass.services.async_call(DOMAIN, "dismiss_for_today", {}, blocking=True)
    await hass.async_block_till_done()
    assert coordinator.current_mode == "dismissed"

    await hass.services.async_call(DOMAIN, "stop_alarm", {}, blocking=True)
    await hass.async_block_till_done()
