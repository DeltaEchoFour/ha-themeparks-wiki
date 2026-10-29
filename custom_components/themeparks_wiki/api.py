"""Small async client for the ThemeParks.wiki REST API."""

from __future__ import annotations

from typing import Any

import aiohttp

from .const import API_BASE_URL

REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)


class ThemeParksError(Exception):
    """Base error for the ThemeParks.wiki client."""


class ThemeParksConnectionError(ThemeParksError):
    """The API could not be reached or returned an unexpected response."""


class ThemeParksAuthError(ThemeParksError):
    """The API rejected the API key."""


class ThemeParksRateLimitError(ThemeParksError):
    """The API returned HTTP 429."""

    def __init__(self, retry_after: float | None) -> None:
        """Store how long the API asked us to wait."""
        super().__init__(
            "Rate limited by ThemeParks.wiki"
            + (f", retry after {retry_after:.0f}s" if retry_after else "")
        )
        self.retry_after = retry_after


class ThemeParksClient:
    """Thin wrapper over the endpoints this integration uses."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str | None = None,
        user_agent: str = "home-assistant-themeparks-wiki",
    ) -> None:
        """Create a client. An empty API key means anonymous access."""
        self._session = session
        self._headers = {"accept": "application/json", "user-agent": user_agent}
        if api_key:
            self._headers["x-api-key"] = api_key

    async def _get(self, path: str) -> dict[str, Any]:
        url = f"{API_BASE_URL}{path}"
        try:
            async with self._session.get(
                url, headers=self._headers, timeout=REQUEST_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise ThemeParksAuthError(
                        f"ThemeParks.wiki rejected the API key (HTTP {resp.status})"
                    )
                if resp.status == 429:
                    raise ThemeParksRateLimitError(
                        _parse_retry_after(resp.headers.get("retry-after"))
                    )
                if resp.status >= 400:
                    raise ThemeParksConnectionError(
                        f"ThemeParks.wiki returned HTTP {resp.status} for {path}"
                    )
                data = await resp.json(content_type=None)
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ThemeParksConnectionError(
                f"Error talking to ThemeParks.wiki: {err}"
            ) from err
        except ValueError as err:
            raise ThemeParksConnectionError(
                f"ThemeParks.wiki returned invalid JSON for {path}"
            ) from err
        if not isinstance(data, dict):
            raise ThemeParksConnectionError(
                f"ThemeParks.wiki returned an unexpected payload for {path}"
            )
        return data

    async def destinations(self) -> list[dict[str, Any]]:
        """Return every destination with its parks."""
        data = await self._get("/destinations")
        return [d for d in data.get("destinations") or [] if d.get("id")]

    async def entity(self, entity_id: str) -> dict[str, Any]:
        """Return one entity document."""
        return await self._get(f"/entity/{entity_id}")

    async def children(self, entity_id: str) -> dict[str, Any]:
        """Return the entity's whole subtree (for a destination or park)."""
        return await self._get(f"/entity/{entity_id}/children")

    async def live(self, entity_id: str) -> dict[str, Any]:
        """Return live data for the entity and everything under it."""
        return await self._get(f"/entity/{entity_id}/live")

    async def schedule(self, entity_id: str) -> dict[str, Any]:
        """Return opening hours for the next 30 days."""
        return await self._get(f"/entity/{entity_id}/schedule")


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None
