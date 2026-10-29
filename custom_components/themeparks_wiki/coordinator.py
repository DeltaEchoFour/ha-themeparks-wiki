"""Data update coordinators for ThemeParks.wiki."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
import logging
import time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ThemeParksAuthError,
    ThemeParksClient,
    ThemeParksError,
    ThemeParksRateLimitError,
)
from .const import (
    CONF_DESTINATION_ID,
    CONF_LIVE_INTERVAL,
    CONF_PARKS,
    CONF_SCHEDULE_INTERVAL,
    DEFAULT_LIVE_INTERVAL,
    DEFAULT_SCHEDULE_INTERVAL,
    DOMAIN,
    ENTITY_TYPE_PARK,
    OTHER_PARK,
    SCHEDULE_EXTRA_HOURS,
    SCHEDULE_INFO,
    SCHEDULE_OPERATING,
    SCHEDULE_PRIVATE_EVENT,
    SCHEDULE_TICKETED_EVENT,
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_PRIVATE_EVENT,
    STATUS_TICKETED_EVENT,
    TOPOLOGY_MAX_AGE,
    TOPOLOGY_MIN_AGE,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class TopologyEntry:
    """Where one API entity sits in the destination."""

    name: str
    entity_type: str
    park_id: str  # a park UUID, or OTHER_PARK


@dataclass(slots=True, frozen=True)
class ScheduleItem:
    """One normalised schedule entry."""

    day: date
    type: str
    description: str | None
    opening: datetime
    closing: datetime
    purchases: tuple[dict[str, Any], ...] = ()

    def covers(self, moment: datetime) -> bool:
        """Return True when the moment falls inside this entry."""
        return self.opening <= moment < self.closing


@dataclass(slots=True)
class ParkSchedule:
    """Thirty days of hours for one park."""

    timezone: ZoneInfo
    items: list[ScheduleItem] = field(default_factory=list)


@dataclass(slots=True)
class ScheduleData:
    """What the schedule coordinator publishes."""

    parks: dict[str, ParkSchedule]
    park_names: dict[str, str]
    topology: dict[str, TopologyEntry]


def _zone(name: str | None, fallback: ZoneInfo) -> ZoneInfo:
    if not name:
        return fallback
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return fallback


def parse_api_datetime(value: str | None, tz: ZoneInfo) -> datetime | None:
    """Parse an API timestamp. Naive values are local to the park."""
    if not value:
        return None
    parsed = dt_util.parse_datetime(value)
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed


def build_topology(children: list[dict[str, Any]]) -> tuple[dict[str, TopologyEntry], dict[str, str]]:
    """Map every child entity to the park it belongs to.

    The children endpoint returns a flat list with parentId links (entity ->
    land -> park -> destination). Anything that never reaches a park is
    filed under OTHER_PARK.
    """
    by_id = {c["id"]: c for c in children if c.get("id")}
    parks = {
        cid: c.get("name") or cid
        for cid, c in by_id.items()
        if c.get("entityType") == ENTITY_TYPE_PARK
    }
    topology: dict[str, TopologyEntry] = {}
    for cid, child in by_id.items():
        if child.get("entityType") == ENTITY_TYPE_PARK:
            continue
        park_id = OTHER_PARK
        parent = child.get("parentId")
        for _ in range(25):
            if not parent:
                break
            if parent in parks:
                park_id = parent
                break
            parent = by_id.get(parent, {}).get("parentId")
        topology[cid] = TopologyEntry(
            name=child.get("name") or cid,
            entity_type=child.get("entityType") or "",
            park_id=park_id,
        )
    return topology, parks


def normalise_schedule(raw: list[dict[str, Any]], tz: ZoneInfo) -> list[ScheduleItem]:
    """Turn raw schedule entries into sorted ScheduleItems."""
    items: list[ScheduleItem] = []
    for entry in raw:
        opening = parse_api_datetime(entry.get("openingTime"), tz)
        closing = parse_api_datetime(entry.get("closingTime"), tz)
        if opening is None or closing is None:
            continue
        day_str = entry.get("date")
        try:
            day = date.fromisoformat(day_str) if day_str else opening.astimezone(tz).date()
        except ValueError:
            day = opening.astimezone(tz).date()
        items.append(
            ScheduleItem(
                day=day,
                type=entry.get("type") or SCHEDULE_INFO,
                description=entry.get("description") or None,
                opening=opening,
                closing=closing,
                purchases=tuple(_purchase(p) for p in entry.get("purchases") or []),
            )
        )
    items.sort(key=lambda i: (i.opening, i.closing))
    return items


def _purchase(raw: dict[str, Any]) -> dict[str, Any]:
    price = raw.get("price") or {}
    formatted = price.get("formatted")
    if not formatted and price.get("amount") is not None:
        formatted = f"{price['amount'] / 100:.2f} {price.get('currency', '')}".strip()
    return {
        "name": raw.get("name"),
        "type": raw.get("type"),
        "price": formatted,
        "available": raw.get("available"),
    }


def _item_dict(item: ScheduleItem) -> dict[str, Any]:
    return {
        "type": item.type,
        "name": item.description,
        "opening_time": item.opening.isoformat(),
        "closing_time": item.closing.isoformat(),
    }


def park_status(schedule: ParkSchedule | None, now: datetime) -> tuple[str, dict[str, Any]]:
    """Return the park status sensor's state and attributes for a moment."""
    if schedule is None:
        return STATUS_CLOSED, {
            "opening_time": None,
            "closing_time": None,
            "schedule_type": None,
            "all_schedules": [],
        }
    tz = schedule.timezone
    today = now.astimezone(tz).date()
    todays = [i for i in schedule.items if i.day == today or i.covers(now)]

    operating = next((i for i in todays if i.type == SCHEDULE_OPERATING), None)
    primary = operating or next((i for i in todays if i.type != SCHEDULE_INFO), None)

    current = [i for i in todays if i.covers(now)]
    current_types = {i.type for i in current}
    if current_types & {SCHEDULE_OPERATING, SCHEDULE_EXTRA_HOURS}:
        state = STATUS_OPEN
    elif SCHEDULE_TICKETED_EVENT in current_types:
        state = STATUS_TICKETED_EVENT
    elif SCHEDULE_PRIVATE_EVENT in current_types:
        state = STATUS_PRIVATE_EVENT
    else:
        state = STATUS_CLOSED

    next_open = next(
        (
            i.opening
            for i in schedule.items
            if i.type == SCHEDULE_OPERATING and i.opening > now
        ),
        None,
    )
    upcoming = [_item_dict(i) | {"date": i.day.isoformat()} for i in schedule.items if i.closing > now]
    attrs: dict[str, Any] = {
        "opening_time": operating.opening.isoformat() if operating else None,
        "closing_time": operating.closing.isoformat() if operating else None,
        "schedule_type": primary.type if primary else None,
        "all_schedules": [_item_dict(i) for i in todays],
        "current_schedules": [_item_dict(i) for i in current],
        "next_opening_time": next_open.isoformat() if next_open else None,
        "purchases": list(operating.purchases) if operating else [],
        "timezone": str(tz),
        "upcoming": upcoming,
    }
    return state, attrs


class ThemeParksScheduleCoordinator(DataUpdateCoordinator[ScheduleData]):
    """Polls opening hours, and the park tree when it is stale."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ThemeParksClient) -> None:
        """Create the coordinator."""
        minutes = entry.options.get(CONF_SCHEDULE_INTERVAL, DEFAULT_SCHEDULE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} schedule",
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self.destination_id: str = entry.data[CONF_DESTINATION_ID]
        self._topology: dict[str, TopologyEntry] = {}
        self._park_names: dict[str, str] = {}
        self._topology_fetched = 0.0
        self.topology_stale = False

    async def _async_update_data(self) -> ScheduleData:
        try:
            age = time.monotonic() - self._topology_fetched
            if (
                not self._topology
                or (self.topology_stale and age > TOPOLOGY_MIN_AGE)
                or age > TOPOLOGY_MAX_AGE
            ):
                await self._refresh_topology()
            parks = await self._fetch_schedules()
        except ThemeParksAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ThemeParksRateLimitError as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except ThemeParksError as err:
            raise UpdateFailed(str(err)) from err
        return ScheduleData(parks=parks, park_names=dict(self._park_names), topology=self._topology)

    async def _refresh_topology(self) -> None:
        try:
            data = await self.client.children(self.destination_id)
        except ThemeParksError:
            if self._topology:
                _LOGGER.debug("Keeping the previous park tree after a failed refresh")
                return
            raise
        self._topology, self._park_names = build_topology(data.get("children") or [])
        self._topology_fetched = time.monotonic()
        self.topology_stale = False

    async def _fetch_schedules(self) -> dict[str, ParkSchedule]:
        fallback_tz = dt_util.get_default_time_zone()
        wanted = set(self.config_entry.options.get(CONF_PARKS) or self._park_names)
        data = await self.client.schedule(self.destination_id)
        dest_tz = _zone(data.get("timezone"), fallback_tz)
        result: dict[str, ParkSchedule] = {}
        for park in data.get("parks") or []:
            pid = park.get("id")
            if not pid:
                continue
            tz = _zone(park.get("timezone"), dest_tz)
            result[pid] = ParkSchedule(tz, normalise_schedule(park.get("schedule") or [], tz))
        # Some destinations do not nest park schedules; ask each park directly.
        for pid in wanted - result.keys():
            try:
                pdata = await self.client.schedule(pid)
            except ThemeParksAuthError:
                raise
            except ThemeParksError as err:
                _LOGGER.debug("No schedule for park %s: %s", pid, err)
                continue
            tz = _zone(pdata.get("timezone"), dest_tz)
            result[pid] = ParkSchedule(tz, normalise_schedule(pdata.get("schedule") or [], tz))
        return result


class ThemeParksLiveCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Polls live wait times, statuses and showtimes for the whole destination."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: ThemeParksClient) -> None:
        """Create the coordinator."""
        seconds = entry.options.get(CONF_LIVE_INTERVAL, DEFAULT_LIVE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} live",
            update_interval=timedelta(seconds=seconds),
        )
        self.client = client
        self.destination_id: str = entry.data[CONF_DESTINATION_ID]
        self.timezone: ZoneInfo = dt_util.get_default_time_zone()

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            data = await self.client.live(self.destination_id)
        except ThemeParksAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ThemeParksRateLimitError as err:
            raise UpdateFailed(str(err), retry_after=err.retry_after) from err
        except ThemeParksError as err:
            raise UpdateFailed(str(err)) from err
        self.timezone = _zone(data.get("timezone"), self.timezone)
        return {e["id"]: e for e in data.get("liveData") or [] if e.get("id")}
