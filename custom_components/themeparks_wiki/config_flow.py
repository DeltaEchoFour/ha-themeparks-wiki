"""Config, options, reconfigure and reauth flows for ThemeParks.wiki."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    ThemeParksAuthError,
    ThemeParksClient,
    ThemeParksError,
    ThemeParksRateLimitError,
)
from .const import (
    CONF_API_KEY,
    CONF_CALENDARS,
    CONF_DESTINATION_ID,
    CONF_DESTINATION_NAME,
    CONF_INCLUDE_OTHER,
    CONF_INCLUDE_RESTAURANTS,
    CONF_INCLUDE_SHOWS,
    CONF_LEGACY_ENTITIES,
    CONF_LIVE_INTERVAL,
    CONF_PARK_CATALOG,
    CONF_PARKS,
    CONF_SCHEDULE_INTERVAL,
    CONF_TAKE_OVER_LEGACY,
    DEFAULT_CALENDARS,
    DEFAULT_INCLUDE_OTHER,
    DEFAULT_INCLUDE_RESTAURANTS,
    DEFAULT_INCLUDE_SHOWS,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_SCHEDULE_INTERVAL,
    DOMAIN,
    LEGACY_DOMAIN,
    MAX_LIVE_INTERVAL,
    MAX_SCHEDULE_INTERVAL,
    MIN_LIVE_INTERVAL,
    MIN_SCHEDULE_INTERVAL,
)
from .coordinator import build_topology

_LOGGER = logging.getLogger(__name__)

CONF_DESTINATION = "destination"
CONF_REMOVE_API_KEY = "remove_api_key"

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


async def _validate_key(hass: HomeAssistant, api_key: str | None) -> list[dict[str, Any]]:
    """Return the destination list, proving the key (or no key) works."""
    client = ThemeParksClient(async_get_clientsession(hass), api_key or None)
    return await client.destinations()


def _error_for(err: ThemeParksError) -> str:
    if isinstance(err, ThemeParksAuthError):
        return "invalid_auth"
    if isinstance(err, ThemeParksRateLimitError):
        return "rate_limited"
    return "cannot_connect"


def _parks_selector(catalog: Mapping[str, str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=pid, label=name)
                for pid, name in sorted(catalog.items(), key=lambda kv: kv[1])
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def default_options(parks: list[str]) -> dict[str, Any]:
    """Options a new entry starts with."""
    return {
        CONF_PARKS: parks,
        CONF_INCLUDE_SHOWS: DEFAULT_INCLUDE_SHOWS,
        CONF_INCLUDE_RESTAURANTS: DEFAULT_INCLUDE_RESTAURANTS,
        CONF_INCLUDE_OTHER: DEFAULT_INCLUDE_OTHER,
        CONF_CALENDARS: DEFAULT_CALENDARS,
        CONF_LIVE_INTERVAL: DEFAULT_LIVE_INTERVAL,
        CONF_SCHEDULE_INTERVAL: DEFAULT_SCHEDULE_INTERVAL,
    }


def find_legacy_entities(
    hass: HomeAssistant, known_ids: set[str], park_ids: set[str]
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Find the old Theme Parks integration's entities for this destination.

    Its unique IDs are "<entry id>_<ThemeParks.wiki id>" for attractions and
    "<entry id>_<park id>_status" for park status, so stripping the entry ID
    gives exactly the unique IDs this integration uses.
    Returns (unique_id -> saved settings, legacy config entry IDs).
    """
    ent_reg = er.async_get(hass)
    found: dict[str, dict[str, Any]] = {}
    entries: set[str] = set()
    for reg in ent_reg.entities.values():
        if reg.platform != LEGACY_DOMAIN or not reg.config_entry_id:
            continue
        prefix = f"{reg.config_entry_id}_"
        if not reg.unique_id.startswith(prefix):
            continue
        key = reg.unique_id[len(prefix) :]
        base = key.removesuffix("_status")
        if key.endswith("_status"):
            if base not in park_ids:
                continue
        elif key not in known_ids:
            continue
        conversation = (reg.options or {}).get("conversation") or {}
        found[key] = {
            "entity_id": reg.entity_id,
            "name": reg.name,
            "icon": reg.icon,
            "area_id": reg.area_id,
            "labels": sorted(reg.labels or []),
            "aliases": [a for a in (reg.aliases or []) if isinstance(a, str)],
            "should_expose": conversation.get("should_expose"),
        }
        entries.add(reg.config_entry_id)
    return found, entries


class ThemeParksConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a ThemeParks.wiki destination."""

    VERSION = 1

    def __init__(self) -> None:
        """Start a flow."""
        self._api_key: str = ""
        self._destinations: dict[str, dict[str, Any]] = {}
        self._destination: dict[str, Any] = {}
        self._parks: list[str] = []
        self._legacy: dict[str, dict[str, Any]] = {}
        self._legacy_entries: set[str] = set()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> ThemeParksOptionsFlow:
        """Options for an existing entry."""
        return ThemeParksOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for an optional API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._api_key = (user_input.get(CONF_API_KEY) or "").strip()
            try:
                destinations = await _validate_key(self.hass, self._api_key)
            except ThemeParksError as err:
                errors["base"] = _error_for(err)
            else:
                self._destinations = {d["id"]: d for d in destinations}
                if not self._destinations:
                    return self.async_abort(reason="no_destinations")
                return await self.async_step_destination()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY, default=""): PASSWORD}),
            errors=errors,
            description_placeholders={"url": "https://www.themeparks.wiki/api"},
        )

    async def async_step_destination(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the resort."""
        if user_input is not None:
            dest_id = user_input[CONF_DESTINATION]
            await self.async_set_unique_id(dest_id)
            self._abort_if_unique_id_configured()
            self._destination = self._destinations[dest_id]
            return await self.async_step_parks()
        options = [
            SelectOptionDict(value=did, label=d.get("name") or did)
            for did, d in sorted(self._destinations.items(), key=lambda kv: kv[1].get("name") or "")
        ]
        return self.async_show_form(
            step_id="destination",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DESTINATION): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                    )
                }
            ),
        )

    def _catalog(self) -> dict[str, str]:
        return {
            p["id"]: p.get("name") or p["id"]
            for p in self._destination.get("parks") or []
            if p.get("id")
        }

    async def async_step_parks(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick which parks to track."""
        catalog = self._catalog()
        errors: dict[str, str] = {}
        if user_input is not None or not catalog:
            self._parks = list(user_input.get(CONF_PARKS, [])) if user_input else []
            if catalog and not self._parks:
                errors[CONF_PARKS] = "no_parks"
            else:
                return await self._async_check_legacy()
        return self.async_show_form(
            step_id="parks",
            data_schema=vol.Schema(
                {vol.Required(CONF_PARKS, default=sorted(catalog)): _parks_selector(catalog)}
            ),
            errors=errors,
            description_placeholders={"destination": self._destination.get("name", "")},
        )

    async def _async_check_legacy(self) -> ConfigFlowResult:
        """Offer to take over the old integration's entity IDs, if it is here."""
        if not any(r.platform == LEGACY_DOMAIN for r in er.async_get(self.hass).entities.values()):
            return self._async_create()
        client = ThemeParksClient(async_get_clientsession(self.hass), self._api_key or None)
        try:
            children = await client.children(self._destination["id"])
        except ThemeParksError as err:
            _LOGGER.debug("Could not read the park tree to match old entities: %s", err)
            return self._async_create()
        topology, parks = build_topology(children.get("children") or [])
        self._legacy, self._legacy_entries = find_legacy_entities(
            self.hass, set(topology), set(parks) | set(self._catalog())
        )
        if not self._legacy:
            return self._async_create()
        return await self.async_step_legacy()

    async def async_step_legacy(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Confirm taking over entity IDs and removing the old integration."""
        if user_input is not None:
            if not user_input.get(CONF_TAKE_OVER_LEGACY):
                self._legacy = {}
                return self._async_create()
            # Removing the old entries frees their entity IDs; setup of the
            # new entry then registers its entities under those same IDs.
            for entry_id in self._legacy_entries:
                if self.hass.config_entries.async_get_entry(entry_id):
                    await self.hass.config_entries.async_remove(entry_id)
            return self._async_create()
        titles = sorted(
            {
                e.title
                for e in (self.hass.config_entries.async_get_entry(i) for i in self._legacy_entries)
                if e
            }
        )
        return self.async_show_form(
            step_id="legacy",
            data_schema=vol.Schema(
                {vol.Required(CONF_TAKE_OVER_LEGACY, default=True): BooleanSelector()}
            ),
            description_placeholders={
                "count": str(len(self._legacy)),
                "old": ", ".join(titles) or "Theme Parks",
            },
        )

    @callback
    def _async_create(self) -> ConfigFlowResult:
        catalog = self._catalog()
        data: dict[str, Any] = {
            CONF_API_KEY: self._api_key,
            CONF_DESTINATION_ID: self._destination["id"],
            CONF_DESTINATION_NAME: self._destination.get("name") or self._destination["id"],
            CONF_PARK_CATALOG: catalog,
        }
        if self._legacy:
            data[CONF_LEGACY_ENTITIES] = self._legacy
        return self.async_create_entry(
            title=data[CONF_DESTINATION_NAME],
            data=data,
            options=default_options(self._parks or sorted(catalog)),
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change or remove the API key."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            new_key = (user_input.get(CONF_API_KEY) or "").strip()
            if user_input.get(CONF_REMOVE_API_KEY):
                new_key = ""
            elif not new_key:
                new_key = entry.data.get(CONF_API_KEY, "")
            try:
                destinations = await _validate_key(self.hass, new_key)
            except ThemeParksError as err:
                errors["base"] = _error_for(err)
            else:
                updates: dict[str, Any] = {CONF_API_KEY: new_key}
                dest = next(
                    (d for d in destinations if d["id"] == entry.data[CONF_DESTINATION_ID]), None
                )
                if dest:
                    updates[CONF_PARK_CATALOG] = {
                        p["id"]: p.get("name") or p["id"] for p in dest.get("parks") or [] if p.get("id")
                    }
                return self.async_update_reload_and_abort(entry, data_updates=updates)
        has_key = bool(entry.data.get(CONF_API_KEY))
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_API_KEY, default=""): PASSWORD,
                    vol.Optional(CONF_REMOVE_API_KEY, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={"current": "an API key" if has_key else "no API key"},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        """The API rejected the stored key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new key, or none."""
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            new_key = (user_input.get(CONF_API_KEY) or "").strip()
            try:
                await _validate_key(self.hass, new_key)
            except ThemeParksError as err:
                errors["base"] = _error_for(err)
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_API_KEY: new_key})
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_API_KEY, default=""): PASSWORD}),
            errors=errors,
        )


class ThemeParksOptionsFlow(OptionsFlowWithReload):
    """Parks, entity types, calendars and update intervals."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show every option on one page."""
        entry = self.config_entry
        catalog: dict[str, str] = dict(entry.data.get(CONF_PARK_CATALOG) or {})
        runtime = getattr(entry, "runtime_data", None)
        if runtime is not None:
            catalog.update(runtime.filter.park_names)
        errors: dict[str, str] = {}
        if user_input is not None:
            if catalog and not user_input.get(CONF_PARKS):
                errors[CONF_PARKS] = "no_parks"
            else:
                user_input[CONF_LIVE_INTERVAL] = int(user_input[CONF_LIVE_INTERVAL])
                user_input[CONF_SCHEDULE_INTERVAL] = int(user_input[CONF_SCHEDULE_INTERVAL])
                return self.async_create_entry(data=user_input)

        opts = entry.options
        schema: dict[Any, Any] = {}
        if catalog:
            schema[vol.Required(CONF_PARKS, default=opts.get(CONF_PARKS) or sorted(catalog))] = (
                _parks_selector(catalog)
            )
        schema.update(
            {
                vol.Required(
                    CONF_INCLUDE_SHOWS, default=opts.get(CONF_INCLUDE_SHOWS, DEFAULT_INCLUDE_SHOWS)
                ): BooleanSelector(),
                vol.Required(
                    CONF_INCLUDE_RESTAURANTS,
                    default=opts.get(CONF_INCLUDE_RESTAURANTS, DEFAULT_INCLUDE_RESTAURANTS),
                ): BooleanSelector(),
                vol.Required(
                    CONF_INCLUDE_OTHER, default=opts.get(CONF_INCLUDE_OTHER, DEFAULT_INCLUDE_OTHER)
                ): BooleanSelector(),
                vol.Required(
                    CONF_CALENDARS, default=opts.get(CONF_CALENDARS, DEFAULT_CALENDARS)
                ): BooleanSelector(),
                vol.Required(
                    CONF_LIVE_INTERVAL, default=opts.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_LIVE_INTERVAL,
                        max=MAX_LIVE_INTERVAL,
                        step=30,
                        unit_of_measurement="s",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_SCHEDULE_INTERVAL,
                    default=opts.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCHEDULE_INTERVAL,
                        max=MAX_SCHEDULE_INTERVAL,
                        step=15,
                        unit_of_measurement="min",
                        mode=NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema), errors=errors)
