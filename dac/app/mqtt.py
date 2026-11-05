"""MQTT discovery for DAC – provides dashboard-friendly sensors.

Home Assistant subscribes to the discovery topics, the app only publishes a
small JSON payload on every change and every 60 s. This is the resource-light
way: no permanent event stream, and the entities survive a restart of the app.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

from .config import settings
from .coordinator import coordinator

log = logging.getLogger("dac.mqtt")

DEVICE_ID = "dac"
DEVICE_NAME = "DAC Wecker"
PUBLISH_INTERVAL = 60

_client: Any = None
_lock = threading.Lock()
_stop = threading.Event()
_thread: threading.Thread | None = None


def _prefix() -> str:
    return str(settings.get("mqtt_discovery_prefix") or "homeassistant")


def _topic(suffix: str = "") -> str:
    base = f"{_prefix()}/sensor/{DEVICE_ID}"
    return f"{base}/{suffix}" if suffix else base


def _device_block() -> dict[str, Any]:
    return {
        "identifiers": [DEVICE_ID],
        "name": DEVICE_NAME,
        "manufacturer": "Dealwirth",
        "model": "DAC – Dynamic Alarm Clock",
        "sw_version": "1.0.0",
    }


SENSORS: list[dict[str, Any]] = [
    {
        "key": "naechster_wecker",
        "name": "Nächster Wecker",
        "icon": "mdi:alarm",
        "unit": None,
        "value": lambda s: (s.get("alarm_target") or "unbekannt"),
    },
    {
        "key": "status",
        "name": "Status",
        "icon": "mdi:alarm-check",
        "unit": None,
        "value": lambda s: s.get("state", "idle"),
    },
    {
        "key": "modus",
        "name": "Modus",
        "icon": "mdi:tune",
        "unit": None,
        "value": lambda s: s.get("mode", "standard"),
    },
    {
        "key": "arbeitsbeginn",
        "name": "Arbeitsbeginn",
        "icon": "mdi:briefcase-clock",
        "unit": None,
        "value": lambda s: (s.get("work_time") or "nicht gesetzt"),
    },
    {
        "key": "weckzeit",
        "name": "Weckzeit",
        "icon": "mdi:alarm-bell",
        "unit": None,
        "value": lambda s: (s.get("alarm_time") or "unbekannt"),
    },
    {
        "key": "urlaub",
        "name": "Urlaub",
        "icon": "mdi:beach",
        "unit": None,
        "value": lambda s: "on" if s.get("vacation") else "off",
    },
    {
        "key": "restzeit_minuten",
        "name": "Restzeit bis Wecker",
        "icon": "mdi:timer-sand",
        "unit": "min",
        "value": None,
    },
]


def _connect() -> Any:
    if not settings.get_bool("mqtt_enabled", False):
        return None
    try:
        import paho.mqtt.client as mqtt
    except Exception as err:  # noqa: BLE001
        log.warning("paho-mqtt nicht verfügbar: %s", err)
        return None
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="dac-app")
    except (AttributeError, TypeError):
        client = mqtt.Client(client_id="dac-app")
    username = str(settings.get("mqtt_username") or "")
    if username:
        client.username_pw_set(username, str(settings.get("mqtt_password") or ""))
    try:
        client.connect(str(settings.get("mqtt_host") or "core-mosquitto"),
                       int(settings.get("mqtt_port", 1883)), 30)
        client.loop_start()
        log.info("DAC MQTT verbunden")
        return client
    except Exception as err:  # noqa: BLE001
        log.warning("DAC MQTT Verbindung fehlgeschlagen: %s", err)
        return None


def publish_discovery() -> None:
    """Publish the discovery configs for all DAC sensors."""
    client = _client
    if client is None:
        return
    device = _device_block()
    for sensor in SENSORS:
        key = sensor["key"]
        payload: dict[str, Any] = {
            "name": sensor["name"],
            "unique_id": f"dac_{key}",
            "state_topic": _topic(f"{key}/state"),
            "availability_topic": _topic("availability"),
            "icon": sensor["icon"],
            "device": device,
        }
        if sensor.get("unit"):
            payload["unit_of_measurement"] = sensor["unit"]
        if sensor["name"] in ("Urlaub", "Wecker aktiv"):
            payload["payload_on"] = "on"
            payload["payload_off"] = "off"
        client.publish(_topic(f"{key}/config"), json.dumps(payload), retain=True)
    client.publish(_topic("availability"), "online", retain=True)


def publish_state() -> None:
    """Publish the current state of all DAC sensors."""
    client = _client
    if client is None:
        return
    state = coordinator.snapshot()
    remaining = None
    if state.get("alarm_target"):
        from datetime import datetime

        try:
            target = datetime.fromisoformat(state["alarm_target"])
            remaining = max(0, int((target - datetime.now().astimezone()).total_seconds() // 60))
        except ValueError:
            remaining = None
    for sensor in SENSORS:
        key = sensor["key"]
        if key == "restzeit_minuten":
            value = remaining if remaining is not None else "unbekannt"
        else:
            value = sensor["value"](state)
        client.publish(_topic(f"{key}/state"), str(value), retain=True)


def _loop() -> None:
    while not _stop.wait(PUBLISH_INTERVAL):
        try:
            publish_state()
        except Exception as err:  # noqa: BLE001
            log.debug("DAC MQTT publish failed: %s", err)


def start() -> None:
    """Connect and start the publish loop (no-op when MQTT is disabled)."""
    global _client, _thread
    with _lock:
        _client = _connect()
        if _client is None:
            return
        publish_discovery()
        publish_state()
        _stop.clear()
        _thread = threading.Thread(target=_loop, name="dac-mqtt", daemon=True)
        _thread.start()


def restart() -> None:
    """Reconnect with (possibly) changed settings."""
    stop()
    start()


def stop() -> None:
    """Disconnect and stop the publish loop."""
    global _client, _thread
    with _lock:
        _stop.set()
        if _thread is not None:
            _thread.join(timeout=2)
            _thread = None
        if _client is not None:
            try:
                _client.publish(_topic("availability"), "offline", retain=True)
                _client.loop_stop()
                _client.disconnect()
            except Exception as err:  # noqa: BLE001
                log.debug("DAC MQTT disconnect failed: %s", err)
            _client = None
    time.sleep(0)
