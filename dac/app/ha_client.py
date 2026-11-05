"""Small async Home Assistant REST client used by the DAC app.

Inside the app the Supervisor token grants access to the Core API via
``http://supervisor/core/api`` – no long-lived token has to be created by the
user. A custom ``ha_url`` / ``ha_token`` (e.g. a remote instance) still works.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import SUPERVISOR_TOKEN, settings

log = logging.getLogger("dac.ha")


class HomeAssistantError(RuntimeError):
    """Raised when the Home Assistant API returns an error."""


class HaClient:
    """Thin wrapper around the Home Assistant REST API."""

    def __init__(self) -> None:
        """Create the client (the base URL is resolved per request)."""
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------- lifecycle
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=20.0)
        return self._client

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    def _base(self) -> str:
        """The API base URL (Supervisor proxy unless overridden)."""
        url = str(settings.get("ha_url") or "http://supervisor/core").rstrip("/")
        if not url.endswith("/api"):
            url = f"{url}/api"
        return url

    def _headers(self) -> dict[str, str]:
        token = str(settings.get("ha_token") or "") or SUPERVISOR_TOKEN
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ----------------------------------------------------------------- reads
    async def api_get(self, path: str) -> Any:
        """GET an API path (relative to ``/api``)."""
        client = await self._get_client()
        url = f"{self._base()}/{path.lstrip('/')}"
        try:
            response = await client.get(url, headers=self._headers())
        except httpx.HTTPError as err:
            raise HomeAssistantError(f"Home Assistant nicht erreichbar: {err}") from err
        if response.status_code >= 400:
            raise HomeAssistantError(f"HA {response.status_code}: {response.text[:200]}")
        return response.json()

    async def states(self) -> list[dict[str, Any]]:
        """All entity states."""
        data = await self.api_get("states")
        return data if isinstance(data, list) else []

    async def state(self, entity_id: str) -> dict[str, Any] | None:
        """A single entity state (None when unknown)."""
        try:
            data = await self.api_get(f"states/{entity_id}")
        except HomeAssistantError:
            return None
        return data if isinstance(data, dict) else None

    async def state_value(self, entity_id: str, default: str = "unknown") -> str:
        """Just the state string of an entity."""
        data = await self.state(entity_id)
        return str(data.get("state")) if data else default

    async def config(self) -> dict[str, Any]:
        """The Home Assistant configuration (version, location, timezone)."""
        try:
            data = await self.api_get("config")
        except HomeAssistantError:
            return {}
        return data if isinstance(data, dict) else {}

    async def services(self) -> list[dict[str, Any]]:
        """All available services."""
        try:
            data = await self.api_get("services")
        except HomeAssistantError:
            return []
        return data if isinstance(data, list) else []

    # ---------------------------------------------------------------- writes
    async def call_service(
        self,
        domain: str,
        service: str,
        data: dict[str, Any] | None = None,
        *,
        return_response: bool = False,
    ) -> Any:
        """Call a Home Assistant service (optionally returning its response)."""
        client = await self._get_client()
        url = f"{self._base()}/services/{domain}/{service}"
        if return_response:
            url += "?return_response"
        try:
            response = await client.post(url, headers=self._headers(), json=data or {})
        except httpx.HTTPError as err:
            raise HomeAssistantError(f"Home Assistant nicht erreichbar: {err}") from err
        if response.status_code >= 400:
            raise HomeAssistantError(
                f"{domain}.{service} fehlgeschlagen ({response.status_code}): "
                f"{response.text[:200]}"
            )
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    async def set_state(
        self, entity_id: str, state: str, attributes: dict[str, Any] | None = None
    ) -> None:
        """Create/update an entity state (used for a status sensor)."""
        await self._set_state(entity_id, state, attributes or {})

    async def _set_state(self, entity_id: str, state: str, attributes: dict[str, Any]) -> None:
        client = await self._get_client()
        url = f"{self._base()}/states/{entity_id}"
        payload = {"state": state, "attributes": attributes}
        try:
            await client.post(url, headers=self._headers(), json=payload)
        except httpx.HTTPError as err:  # pragma: no cover – best effort
            log.debug("DAC could not set %s: %s", entity_id, err)


ha = HaClient()
