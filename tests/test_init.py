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
    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
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
    assert config_entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_set_work_time_service_updates_sensor(
    hass: HomeAssistant, config_entry: MockConfigEntry, options: dict
) -> None:
    """Calling dac.set_work_time schedules the alarm on the sensor."""
    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
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
    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()

    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    await coordinator.async_set_work_time(FakeCall({"time": "23:59"}))

    await hass.services.async_call(DOMAIN, "dismiss_for_today", {}, blocking=True)
    await hass.async_block_till_done()
    assert coordinator.current_mode == "dismissed"

    await hass.services.async_call(DOMAIN, "stop_alarm", {}, blocking=True)
    await hass.async_block_till_done()


async def test_second_entry_keeps_services_on_unload(
    hass: HomeAssistant, options: dict
) -> None:
    """Unloading one of two entries must keep the shared services alive."""
    first = MockConfigEntry(domain=DOMAIN, title="A", data={}, options=options)
    second = MockConfigEntry(domain=DOMAIN, title="B", data={}, options=options)
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
        # Setting up the config-entry manager loads all registered entries.
        await hass.config_entries.async_setup(first.entry_id)
        await hass.async_block_till_done()

    assert len(hass.data[DOMAIN]) == 2
    assert hass.services.has_service(DOMAIN, "set_work_time")

    await hass.config_entries.async_unload(first.entry_id)
    await hass.async_block_till_done()

    # The second entry is still loaded -> its services must survive.
    assert second.entry_id in hass.data[DOMAIN]
    assert hass.services.has_service(DOMAIN, "set_work_time")


async def test_service_requires_entry_id_with_multiple_entries(
    hass: HomeAssistant, options: dict
) -> None:
    """With two entries the service must not guess – config_entry_id is required."""
    from homeassistant.exceptions import HomeAssistantError

    first = MockConfigEntry(domain=DOMAIN, title="A", data={}, options=options)
    second = MockConfigEntry(domain=DOMAIN, title="B", data={}, options=options)
    first.add_to_hass(hass)
    second.add_to_hass(hass)

    with patch("custom_components.dac.async_setup_frontend", new=AsyncMock()):
        await hass.config_entries.async_setup(first.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "set_work_time", {"time": "08:00"}, blocking=True
        )

    # Passing the entry id resolves the ambiguity.
    await hass.services.async_call(
        DOMAIN,
        "set_work_time",
        {"time": "08:00", "config_entry_id": second.entry_id},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.data[DOMAIN][second.entry_id]._work_time is not None
