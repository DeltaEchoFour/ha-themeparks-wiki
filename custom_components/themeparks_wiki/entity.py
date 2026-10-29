"""Shared entity helpers for ThemeParks.wiki."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import (
    ATTRIBUTION,
    CONF_CALENDARS,
    CONF_DESTINATION_ID,
    CONF_DESTINATION_NAME,
    CONF_INCLUDE_OTHER,
    CONF_INCLUDE_RESTAURANTS,
    CONF_INCLUDE_SHOWS,
    CONF_PARK_CATALOG,
    CONF_PARKS,
    DEFAULT_CALENDARS,
    DEFAULT_INCLUDE_OTHER,
    DEFAULT_INCLUDE_RESTAURANTS,
    DEFAULT_INCLUDE_SHOWS,
    DOMAIN,
    ENTITY_TYPE_ATTRACTION,
    ENTITY_TYPE_RESTAURANT,
    ENTITY_TYPE_SHOW,
    MANUFACTURER,
    OTHER_PARK,
)

if TYPE_CHECKING:
    from .coordinator import ThemeParksScheduleCoordinator

STATUS_SUFFIX = "_status"
CALENDAR_SUFFIX = "_calendar"


class EntityFilter:
    """Decides which parks and entity types this entry exposes."""

    def __init__(self, entry: ConfigEntry, schedule: ThemeParksScheduleCoordinator) -> None:
        """Read the entry's options."""
        self._entry = entry
        self._schedule = schedule
        self.destination_id: str = entry.data[CONF_DESTINATION_ID]
        self.destination_name: str = entry.data.get(CONF_DESTINATION_NAME) or "Theme park"
        opts = entry.options
        self.types = {ENTITY_TYPE_ATTRACTION}
        if opts.get(CONF_INCLUDE_SHOWS, DEFAULT_INCLUDE_SHOWS):
            self.types.add(ENTITY_TYPE_SHOW)
        if opts.get(CONF_INCLUDE_RESTAURANTS, DEFAULT_INCLUDE_RESTAURANTS):
            self.types.add(ENTITY_TYPE_RESTAURANT)
        self.include_other: bool = opts.get(CONF_INCLUDE_OTHER, DEFAULT_INCLUDE_OTHER)
        self.calendars: bool = opts.get(CONF_CALENDARS, DEFAULT_CALENDARS)
        # Live entries the park tree did not know about; each asks for one
        # tree refresh, never more.
        self._unknown: set[str] = set()

    @property
    def park_names(self) -> dict[str, str]:
        """Every park in the destination, id -> name."""
        names: dict[str, str] = dict(self._entry.data.get(CONF_PARK_CATALOG) or {})
        if self._schedule.data:
            names.update(self._schedule.data.park_names)
        return names

    @property
    def selected_parks(self) -> set[str]:
        """Parks the user chose; all of them when none were chosen."""
        chosen = self._entry.options.get(CONF_PARKS)
        return set(chosen) if chosen else set(self.park_names)

    def park_of(self, api_id: str) -> str | None:
        """Return the park an API entity sits in, or None when unknown."""
        if not self._schedule.data:
            return None
        node = self._schedule.data.topology.get(api_id)
        return node.park_id if node else None

    def park_allowed(self, park_id: str) -> bool:
        """Whether entities in this park (or the non-park area) are wanted."""
        if park_id == OTHER_PARK:
            return self.include_other
        return park_id in self.selected_parks

    def live_park(self, api_id: str, item: dict | None = None) -> str | None:
        """The park for a live entry: its own parkId first, then the park tree."""
        if item and "parkId" in item:
            pid = item.get("parkId")
            if not pid:
                return OTHER_PARK
            if pid in self.park_names:
                return pid
        return self.park_of(api_id)

    def allows_live(self, api_id: str, item: dict) -> bool:
        """Whether a live-data entry should get a sensor."""
        if item.get("entityType") not in self.types:
            return False
        park_id = self.live_park(api_id, item)
        if park_id is None:
            # New to the API since the park tree was read; read it again once.
            if api_id not in self._unknown:
                self._unknown.add(api_id)
                self._schedule.topology_stale = True
            return False
        return self.park_allowed(park_id)

    def allows_unique_id(self, unique_id: str, domain: str, strict: bool = False) -> bool:
        """Whether a registry entry with this unique ID should exist."""
        if unique_id.endswith(STATUS_SUFFIX):
            return domain == Platform.SENSOR and unique_id[: -len(STATUS_SUFFIX)] in self.selected_parks
        if unique_id.endswith(CALENDAR_SUFFIX):
            return (
                domain == Platform.CALENDAR
                and self.calendars
                and unique_id[: -len(CALENDAR_SUFFIX)] in self.selected_parks
            )
        node = self._schedule.data.topology.get(unique_id) if self._schedule.data else None
        if node is None:
            # Unknown to the park tree: keep it on cleanup, skip it on adoption.
            return not strict
        return node.entity_type in self.types and self.park_allowed(node.park_id)

    def device_ids(self) -> set[str]:
        """Device identifiers that should stay attached to this entry."""
        return self.selected_parks | {self.destination_id}

    def device_info(self, park_id: str) -> DeviceInfo:
        """Device for a park, or for the destination itself."""
        if park_id == OTHER_PARK or park_id == self.destination_id:
            return DeviceInfo(
                identifiers={(DOMAIN, self.destination_id)},
                name=self.destination_name,
                manufacturer=MANUFACTURER,
                model="Destination",
                entry_type=DeviceEntryType.SERVICE,
                configuration_url="https://www.themeparks.wiki",
            )
        return DeviceInfo(
            identifiers={(DOMAIN, park_id)},
            name=self.park_names.get(park_id, park_id),
            manufacturer=MANUFACTURER,
            model="Theme park",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, self.destination_id),
            configuration_url="https://www.themeparks.wiki",
        )


ENTITY_ATTRIBUTION = ATTRIBUTION
