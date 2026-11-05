"""DAC – Dynamic Alarm Clock, Home Assistant App (FastAPI).

Serves the Ingress UI and a small JSON API. All alarm logic lives in
``coordinator.py``; MQTT discovery provides the dashboard sensors.
"""
from __future__ import annotations

import logging
import os
import re
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, mqtt
from .config import EDITABLE, settings
from .coordinator import coordinator
from .ha_client import HomeAssistantError, ha
from .logic import parse_time_str

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("dac")

STATIC_DIR = Path(__file__).parent / "static"


async def _apply_timezone() -> None:
    """Adopt the Home Assistant timezone (the container may run in UTC).

    Without this an alarm computed at 05:45 in a UTC container would be stored
    as 05:45 UTC – two hours off for a Europe/Berlin instance.
    """
    config = await ha.config()
    tz = str(config.get("time_zone") or "").strip()
    if not tz:
        return
    os.environ["TZ"] = tz
    try:
        time.tzset()
    except AttributeError:  # pragma: no cover – not on Windows
        return
    log.info("DAC Zeitzone auf %s gesetzt", tz)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start the scheduler and MQTT, tear both down on shutdown."""
    log.info("DAC App %s startet", __version__)
    await _apply_timezone()
    mqtt.start()
    await coordinator.start()
    yield
    await coordinator.stop()
    mqtt.stop()
    await ha.aclose()


app = FastAPI(title="DAC – Dynamic Alarm Clock", version=__version__, lifespan=lifespan)

# Ingress requests always come from the Supervisor; local development in a
# container needs the extra origins, but no credentials are transferred.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def ingress_headers(request: Request, call_next: Any) -> Response:
    """Pass the Ingress path through and add security headers."""
    response = await call_next(request)
    ingress_path = request.headers.get("X-Ingress-Path")
    if ingress_path:
        response.headers["X-Ingress-Path"] = ingress_path
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    return response


def _base_href(request: Request) -> str:
    """The base path for the page's ``<base>`` element.

    Home Assistant serves the UI under ``/api/hassio_ingress/<token>/`` and
    passes that prefix in the ``X-Ingress-Path`` header (the value changes on
    every restart). Writing it server-side matters: the browser reads ``<base>``
    during preload, so setting it later via JavaScript would load assets from
    the wrong, nested URL.
    """
    header = (request.headers.get("X-Ingress-Path") or "").strip("/")
    return f"/{header}/" if header else "/"


def _render_index(request: Request) -> Response:
    """Serve the UI with the correct ``<base>`` for Ingress."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return JSONResponse(status_code=503, content={"detail": "Oberfläche fehlt"})
    html = index_file.read_text(encoding="utf-8")
    base = f'<base href="{_base_href(request)}" />'
    if re.search(r"<base\s[^>]*>", html, re.IGNORECASE):
        html = re.sub(r"<base\s[^>]*>", base, html, count=1, flags=re.IGNORECASE)
    else:
        html = re.sub(r"(<head[^>]*>)", r"\1\n    " + base, html, count=1, flags=re.IGNORECASE)
    return HTMLResponse(content=html, headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


async def _json_body(request: Request) -> dict[str, Any]:
    """Read a JSON object body (an empty/malformed body counts as empty)."""
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


@app.get("/")
async def index(request: Request) -> Response:
    """The Ingress UI."""
    return _render_index(request)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness probe used by the Supervisor."""
    return {"ok": True, "version": __version__}


@app.get("/api/state")
async def get_state() -> dict[str, Any]:
    """Current alarm state, settings and live entity values."""
    state = coordinator.snapshot()
    echo = None
    if coordinator.alexa.player:
        echo_state = await ha.state(coordinator.alexa.player)
        echo = {
            "player": coordinator.alexa.player,
            "available": echo_state is not None,
            "volume": (echo_state or {}).get("attributes", {}).get("volume_level"),
        }
    return {
        "version": __version__,
        "state": state,
        "settings": settings.all(),
        "alexa": {
            "enabled": coordinator.alexa.enabled,
            "player": coordinator.alexa.player,
            "helper": coordinator.alexa.helper,
            "gate": coordinator.alexa.gate_boolean,
            "gate_on": await coordinator.alexa.gate_on(),
            "stored_alarm": await coordinator.alexa.stored_alarm(),
            "stop_word": coordinator.alexa.stop_word,
            "echo": echo,
        },
        "ha": await ha.config(),
    }


@app.get("/api/entities")
async def get_entities() -> dict[str, Any]:
    """Entity suggestions for the pickers (grouped by domain)."""
    try:
        states = await ha.states()
    except HomeAssistantError as err:
        raise HTTPException(status_code=502, detail=str(err)) from err
    groups: dict[str, list[dict[str, str]]] = {}
    for state in states:
        entity_id = str(state.get("entity_id") or "")
        if "." not in entity_id:
            continue
        domain = entity_id.split(".", 1)[0]
        if domain in ("zone", "sun", "persistent_notification", "update", "tts", "stt"):
            continue
        name = str((state.get("attributes") or {}).get("friendly_name") or entity_id)
        groups.setdefault(domain, []).append({"entity_id": entity_id, "name": name})
    for items in groups.values():
        items.sort(key=lambda item: item["name"].lower())
    return {"groups": groups}


@app.post("/api/settings")
async def post_settings(request: Request) -> dict[str, Any]:
    """Apply changed settings and re-evaluate the schedule."""
    changes = await _json_body(request)
    unknown = [key for key in changes if key not in EDITABLE]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unbekannte Einstellung: {', '.join(unknown)}")
    settings.update(changes)
    coordinator.reschedule()
    await coordinator.save_state()
    mqtt.restart()
    return {"ok": True, "settings": settings.all()}


@app.post("/api/action")
async def post_action(request: Request) -> dict[str, Any]:
    """Run a panel action (set work time, stop, mode, test alarm, …)."""
    payload = await _json_body(request)
    action = str(payload.get("action") or "")
    try:
        if action == "set_work_time":
            value = str(payload.get("time") or "")
            if not value:
                raise HTTPException(status_code=400, detail="Zeit fehlt")
            await coordinator.set_work_time(value, payload.get("day"))
            return {"ok": True, "message": f"Arbeitsbeginn {value[:5]} gespeichert"}

        if action == "clear_work_time":
            await coordinator.clear_work_time()
            return {"ok": True, "message": "Arbeitsbeginn gelöscht"}

        if action == "stop":
            await coordinator.stop_alarm()
            return {"ok": True, "message": "Wecker gestoppt"}

        if action == "mode":
            mode = str(payload.get("mode") or "standard")
            if mode not in ("standard", "dismissed", "vacation"):
                raise HTTPException(status_code=400, detail="Unbekannter Modus")
            await coordinator.set_mode(mode)
            return {"ok": True, "message": f"Modus: {mode}"}

        if action == "dismiss":
            await coordinator.dismiss_for_today(payload.get("day"))
            return {"ok": True, "message": "Für heute aus"}

        if action == "test_start":
            await coordinator.start_test_alarm(payload.get("minutes"))
            return {"ok": True, "message": "Testwecker gestartet"}

        if action == "test_cancel":
            await coordinator.cancel_test_alarm()
            return {"ok": True, "message": "Testwecker abgebrochen"}

        if action == "alexa_set":
            value = payload.get("time") or coordinator.desired_alarm_text()
            if not value:
                raise HTTPException(status_code=400, detail="Kein Wecker berechnet")
            await coordinator.set_alexa_alarm(str(value))
            return {"ok": True, "message": f"Wecker {str(value)[:5]} auf Echo gestellt"}

        if action == "alexa_clear":
            await coordinator.alexa.async_clear_own()
            return {"ok": True, "message": "Echo-Wecker gelöscht"}

        if action == "alexa_sync":
            await coordinator.alexa.async_sync(force=True)
            return {"ok": True, "message": "Echo-Wecker abgeglichen"}

        raise HTTPException(status_code=400, detail=f"Unbekannte Aktion: {action}")
    except (HomeAssistantError, ValueError) as err:
        raise HTTPException(status_code=502, detail=str(err)) from err


@app.get("/api/simulate")
async def simulate(at: str | None = None, work: str | None = None) -> dict[str, Any]:
    """Dry-run: show what DAC would do (error-source simulation, no side effects).

    ``at`` is an ISO time ('2026-11-06T05:30'), ``work`` an optional work time
    ('06:45'). Nothing is changed – this is for verifying the logic safely.
    """
    from datetime import datetime

    from .logic import compute_alarm_time, default_resolution

    now = datetime.fromisoformat(at).astimezone() if at else datetime.now().astimezone()
    if work:
        try:
            work_time = parse_time_str(work)
        except ValueError as err:
            raise HTTPException(status_code=400, detail=str(err)) from err
        target = datetime.combine(now.date(), compute_alarm_time(work_time, coordinator.offset_minutes),
                                  tzinfo=now.tzinfo)
        if target <= now:
            target += __import__("datetime").timedelta(days=1)
        return {
            "at": now.isoformat(),
            "work_time": work_time.strftime("%H:%M"),
            "alarm_time": compute_alarm_time(work_time, coordinator.offset_minutes).strftime("%H:%M"),
            "alarm_target": target.isoformat(),
            "offset_minutes": coordinator.offset_minutes,
        }
    day, alarm_time = default_resolution(now, coordinator.default_alarm_time, coordinator.cutoff_time)
    return {
        "at": now.isoformat(),
        "mode": "default",
        "default_alarm_time": coordinator.default_alarm_time.strftime("%H:%M"),
        "cutoff_time": coordinator.cutoff_time.strftime("%H:%M"),
        "alarm_day": day.isoformat() if day else None,
        "alarm_time": alarm_time.strftime("%H:%M") if alarm_time else None,
        "awaiting_input": day is None,
    }


@app.get("/api/help")
async def help_page() -> dict[str, Any]:
    """Short setup guide shown in the UI's help tab."""
    return {
        "sections": [
            {
                "title": "So funktioniert DAC",
                "text": (
                    "DAC rechnet aus dem Arbeitsbeginn minus Offset die Weckzeit. "
                    "Stelle abends einfach deine Arbeitszeit – der Echo-Wecker wird "
                    "automatisch gestellt. Ohne Arbeitszeit klingelt der Standard-Wecker."
                ),
            },
            {
                "title": "Alexa / Echo einrichten",
                "text": (
                    "Die alexa_media Integration installieren, dann hier den Echo "
                    "(media_player) auswählen. DAC stellt auf dem Echo einen echten "
                    "Wecker – er klingelt auch, wenn Home Assistant aus ist."
                ),
            },
            {
                "title": "Urlaub & Feiertage",
                "text": (
                    "Kalender auswählen und Stichwörter festlegen (z. B. urlaub, "
                    "feiertag). Findet DAC ein passendes Ereignis, bleibt der Wecker aus."
                ),
            },
            {
                "title": "Abend-Erinnerung",
                "text": (
                    "Ist bis zur Erinnerungszeit keine Arbeitszeit gesetzt, schickt DAC "
                    "eine Nachricht und sagt es optional leise auf dem Echo."
                ),
            },
            {
                "title": "Testwecker",
                "text": (
                    "Über „Testwecker“ klingelt der Wecker in N Minuten mit Licht und "
                    "Echo – so lässt sich alles gefahrlos prüfen."
                ),
            },
        ]
    }


@app.exception_handler(HomeAssistantError)
async def ha_error_handler(_request, exc: HomeAssistantError) -> JSONResponse:
    """Return a readable error instead of a stack trace."""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
    """Log unexpected errors and answer with a readable message."""
    log.exception("DAC: unerwarteter Fehler bei %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Interner Fehler", "hint": "Bitte das App-Protokoll prüfen."},
    )


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(request: Request, full_path: str) -> Response:
    """Serve static files, otherwise fall back to the UI (single page app)."""
    candidate = (STATIC_DIR / full_path).resolve()
    if full_path and candidate.is_file() and str(candidate).startswith(str(STATIC_DIR.resolve())):
        return Response(content=candidate.read_bytes(), media_type=_media_type(candidate))
    return _render_index(request)


_MEDIA_TYPES = {
    ".css": "text/css",
    ".js": "application/javascript",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".json": "application/json",
}


def _media_type(path: Path) -> str:
    return _MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
