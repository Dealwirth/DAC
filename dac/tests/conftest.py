"""Shared test setup for the DAC app tests.

``DAC_DATA`` is pointed at a temporary directory *before* the app modules are
imported, so no test ever writes to /data.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="dac-test-"))
os.environ["DAC_DATA"] = str(_TMP)
os.environ.setdefault("SUPERVISOR_TOKEN", "test-token")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def _fresh_settings(tmp_path, monkeypatch):
    """Give every test its own settings and state file."""
    from app import config

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    config.settings._data = dict(config.DEFAULTS)
    config.settings._normalize()

    import app.coordinator as coordinator_module

    monkeypatch.setattr(coordinator_module, "STATE_FILE", tmp_path / "state.json")
    yield


@pytest.fixture
def fake_ha(monkeypatch):
    """An in-process Home Assistant stand-in for the app's REST client.

    The real ``httpx`` client of the shared singleton is given a mock transport,
    so URL building, headers and error paths are exercised – only the remote
    server is fake. All modules share the same singleton, so patching it once
    covers the coordinator, the Alexa bridge and the API.
    """
    import json as _json

    import httpx
    from app import ha_client

    class FakeHa:
        """Records service calls and serves entity states."""

        def __init__(self) -> None:
            self.states: dict[str, dict] = {}
            self.calls: list[tuple[str, str, dict]] = []
            self.config = {"version": "2026.10.4", "location_name": "Zuhause"}
            self.fail_domains: set[str] = set()

        def set_state(self, entity_id, state, attributes=None) -> None:
            self.states[entity_id] = {
                "entity_id": entity_id,
                "state": state,
                "attributes": attributes or {},
            }

        def calls_for(self, domain: str, service: str | None = None) -> list[dict]:
            return [
                data
                for dom, ser, data in self.calls
                if dom == domain and (service is None or ser == service)
            ]

        def _apply(self, domain: str, service: str, data: dict) -> None:
            """Mirror the entity updates a real HA would perform."""
            if domain == "input_text" and service == "set_value":
                entity = data.get("entity_id")
                if entity:
                    self.set_state(entity, str(data.get("value", "")))
            elif domain == "input_boolean":
                entity = data.get("entity_id")
                if entity:
                    self.set_state(entity, "on" if service == "turn_on" else "off")

        def _handler(self, request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/api/config"):
                return httpx.Response(200, json=self.config)
            if path.endswith("/api/states"):
                return httpx.Response(200, json=list(self.states.values()))
            if "/api/states/" in path:
                entity_id = path.rsplit("/api/states/", 1)[1]
                if request.method == "POST":
                    payload = _json.loads(request.content or b"{}")
                    self.states[entity_id] = {
                        "entity_id": entity_id,
                        "state": payload.get("state"),
                        "attributes": payload.get("attributes") or {},
                    }
                if entity_id not in self.states:
                    return httpx.Response(404, json={"message": "not found"})
                return httpx.Response(200, json=self.states[entity_id])
            if "/api/services/" in path:
                rest = path.rsplit("/api/services/", 1)[1]
                domain, _, service = rest.partition("/")
                data = _json.loads(request.content or b"{}")
                self.calls.append((domain, service, data))
                if domain in self.fail_domains:
                    return httpx.Response(500, text="boom")
                self._apply(domain, service, data)
                if "return_response" in str(request.url):
                    return httpx.Response(200, json={"changed_states": []})
                return httpx.Response(200, json=[])
            return httpx.Response(404, json={"message": "unknown"})

    fake = FakeHa()
    client = httpx.AsyncClient(transport=httpx.MockTransport(fake._handler))
    monkeypatch.setattr(ha_client.ha, "_client", client)
    monkeypatch.setattr(ha_client.settings, "_data", {"ha_url": "http://ha.local", "ha_token": "t"})
    yield fake
