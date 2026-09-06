"""Fixtures for DAC tests – the hass fixture comes from
pytest_homeassistant_custom_component (loaded via its entry point)."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
import pytest_socket
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Windows: The HA test plugin blocks all sockets except AF_UNIX, but the
# Windows asyncio event loop needs an AF_INET socket pair (self-pipe) to work
# at all. DAC's tests make no network calls, so we simply keep sockets open.
pytest_socket.disable_socket = lambda *args, **kwargs: None  # type: ignore[assignment]

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

from custom_components.dac.const import (
    DOMAIN,
    CONF_ALARM_LIGHTS,
    CONF_ALARM_VOLUME,
    CONF_DEFAULT_ALARM_TIME,
    CONF_MEDIA_PLAYERS,
    CONF_NOTIFIER,
    CONF_OFFSET,
    CONF_REMINDER_TEXT,
    CONF_REMINDER_TIME,
    CONF_VACATION_CALENDARS,
    DEFAULT_ALARM_TIME,
    DEFAULT_ALARM_VOLUME,
    DEFAULT_OFFSET_MINUTES,
    DEFAULT_REMINDER_TEXT,
    DEFAULT_REMINDER_TIME,
)
from custom_components.dac.coordinator import DacCoordinator
from custom_components.dac.store import DacStore


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make the custom component discoverable to the test hass."""
    yield


@pytest.fixture(autouse=True)
def mock_frontend_setup():
    """Skip the real frontend setup (hass_frontend is not installed in tests)."""
    with patch("homeassistant.components.frontend.async_setup", return_value=True):
        yield


@pytest.fixture(autouse=True)
def berlin_tz(hass: HomeAssistant):
    """Run the test hass in Europe/Berlin (DAC's primary audience).

    freezegun freezes UTC, so freeze_time strings in tests are UTC.
    """
    previous = dt_util.DEFAULT_TIME_ZONE
    dt_util.set_default_time_zone(ZoneInfo("Europe/Berlin"))
    yield
    dt_util.set_default_time_zone(previous)


@pytest.fixture
def options() -> dict[str, Any]:
    """Standard options as they would come from a config entry."""
    return {
        CONF_DEFAULT_ALARM_TIME: DEFAULT_ALARM_TIME,
        CONF_OFFSET: DEFAULT_OFFSET_MINUTES,
        CONF_REMINDER_TIME: DEFAULT_REMINDER_TIME,
        CONF_REMINDER_TEXT: DEFAULT_REMINDER_TEXT,
        CONF_NOTIFIER: "notify.test",
        CONF_ALARM_LIGHTS: ["light.alarm"],
        CONF_MEDIA_PLAYERS: ["media_player.alarm"],
        CONF_VACATION_CALENDARS: ["calendar.vac"],
        CONF_ALARM_VOLUME: DEFAULT_ALARM_VOLUME,
    }


@pytest.fixture
def config_entry(hass: HomeAssistant, options: dict[str, Any]) -> MockConfigEntry:
    """A DAC config entry carrying the test options."""
    entry = MockConfigEntry(domain=DOMAIN, title="DAC", data={}, options=options)
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def store(hass: HomeAssistant) -> DacStore:
    return DacStore(hass, "test_entry")


@pytest.fixture
async def coordinator(
    hass: HomeAssistant, config_entry: MockConfigEntry, store: DacStore
):
    """A coordinator on a real (test) hass, with all timers live."""
    from collections.abc import AsyncIterator

    coord = DacCoordinator(hass, config_entry, store=store)
    await hass.async_block_till_done()  # drain the startup vacation check
    yield coord
    coord.async_shutdown()


@pytest.fixture
def recorded(hass: HomeAssistant) -> list[tuple[str, str, dict]]:
    """Record light / media_player / notify service calls made by DAC."""
    calls: list[tuple[str, str, dict]] = []
    registry_cls = type(hass.services)
    real_call = registry_cls.async_call

    async def spy(self, domain, service, service_data=None, **kwargs):
        if domain in ("light", "media_player", "notify"):
            calls.append((domain, service, dict(service_data or {})))
            return None
        return await real_call(self, domain, service, service_data, **kwargs)

    with patch.object(registry_cls, "async_call", autospec=True, side_effect=spy):
        yield calls


class FakeCall:
    """Minimal ServiceCall stand-in for internal coordinator calls."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
