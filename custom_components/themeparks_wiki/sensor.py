"""Wait time and park status sensors for ThemeParks.wiki."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import Platform, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ThemeParksConfigEntry
from .const import (
    ATTRIBUTION,
    DOMAIN,
    ENTITY_TYPE_RESTAURANT,
    ENTITY_TYPE_SHOW,
    OTHER_PARK,
)
from .coordinator import (
    ThemeParksLiveCoordinator,
    ThemeParksScheduleCoordinator,
    park_status,
    parse_api_datetime,
)
from .entity import STATUS_SUFFIX, EntityFilter

PARALLEL_UPDATES = 0

ICONS = {
    ENTITY_TYPE_SHOW: "mdi:drama-masks",
    ENTITY_TYPE_RESTAURANT: "mdi:silverware-fork-knife",
}
DEFAULT_ICON = "mdi:ferris-wheel"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemeParksConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors, and add new attractions as the API reports them."""
    data = entry.runtime_data
    flt = data.filter
    live = data.live
    schedule = data.schedule

    status_sensors = [
        ParkStatusSensor(schedule, flt, park_id)
        for park_id in sorted(flt.selected_parks)
        if park_id in flt.park_names
    ]
    async_add_entities(status_sensors)

    known: set[str] = set()

    # Entities that existed before but are missing from the current live feed
    # (a closed ride, an off-season show) still get created, as "unknown".
    ent_reg = er.async_get(hass)
    restored: list[WaitTimeSensor] = []
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        uid = reg_entry.unique_id
        if reg_entry.domain != Platform.SENSOR or uid.endswith(STATUS_SUFFIX):
            continue
        if uid in live.data or not flt.allows_unique_id(uid, Platform.SENSOR, strict=True):
            continue
        node = schedule.data.topology[uid]
        known.add(uid)
        restored.append(WaitTimeSensor(live, flt, uid, node.name, node.entity_type))
    if restored:
        async_add_entities(restored)

    @callback
    def _add_new() -> None:
        new: list[WaitTimeSensor] = []
        for api_id, item in (live.data or {}).items():
            if api_id in known:
                continue
            if not flt.allows_live(api_id, item):
                continue
            known.add(api_id)
            new.append(
                WaitTimeSensor(live, flt, api_id, item.get("name") or api_id, item.get("entityType"))
            )
        if new:
            async_add_entities(new)
        if schedule.topology_stale:
            entry.async_create_background_task(
                hass, schedule.async_request_refresh(), f"{DOMAIN} topology refresh"
            )

    _add_new()
    entry.async_on_unload(live.async_add_listener(_add_new))
    entry.async_on_unload(schedule.async_add_listener(_add_new))


class WaitTimeSensor(CoordinatorEntity[ThemeParksLiveCoordinator], SensorEntity):
    """Posted standby wait for one attraction, show or restaurant."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset({"showtimes"})

    def __init__(
        self,
        coordinator: ThemeParksLiveCoordinator,
        flt: EntityFilter,
        api_id: str,
        name: str,
        entity_type: str | None,
    ) -> None:
        """Create the sensor."""
        super().__init__(coordinator)
        self._flt = flt
        self._api_id = api_id
        self._fallback_name = name
        self._entity_type = entity_type
        self._attr_unique_id = api_id
        self._attr_icon = ICONS.get(entity_type or "", DEFAULT_ICON)
        park_id = flt.live_park(api_id, coordinator.data.get(api_id) if coordinator.data else None)
        park_id = park_id or OTHER_PARK
        self._park_id = park_id
        self._attr_device_info = flt.device_info(park_id)

    @property
    def _item(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get(self._api_id) or {}

    @property
    def name(self) -> str:
        """The attraction's name as the API reports it."""
        return self._item.get("name") or self._fallback_name

    @property
    def native_value(self) -> int | None:
        """Posted standby wait in minutes."""
        standby = (self._item.get("queue") or {}).get("STANDBY") or {}
        wait = standby.get("waitTime")
        return int(wait) if isinstance(wait, (int, float)) else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Status, other queues and showtimes."""
        item = self._item
        tz = self.coordinator.timezone
        if self._park_id == OTHER_PARK:
            park_name = self._flt.destination_name
            park_id = None
        else:
            park_name = self._flt.park_names.get(self._park_id, self._park_id)
            park_id = self._park_id
        attrs: dict[str, Any] = {
            "attraction_name": self.name,
            "park_name": park_name,
            "park_id": park_id,
            "destination_name": self._flt.destination_name,
            "entity_type": item.get("entityType") or self._entity_type,
            "status": item.get("status"),
            "last_updated": item.get("lastUpdated"),
        }
        queue = item.get("queue") or {}
        if (single := queue.get("SINGLE_RIDER")) is not None:
            attrs["single_rider_wait"] = single.get("waitTime")
        if (paid_standby := queue.get("PAID_STANDBY")) is not None:
            attrs["paid_standby_wait"] = paid_standby.get("waitTime")
        if (ret := queue.get("RETURN_TIME")) is not None:
            attrs["return_time_state"] = ret.get("state")
            attrs["return_time_start"] = ret.get("returnStart")
            attrs["return_time_end"] = ret.get("returnEnd")
        if (paid := queue.get("PAID_RETURN_TIME")) is not None:
            attrs["paid_return_time_state"] = paid.get("state")
            attrs["paid_return_time_start"] = paid.get("returnStart")
            attrs["paid_return_time_end"] = paid.get("returnEnd")
            price = paid.get("price") or {}
            attrs["paid_return_time_price"] = price.get("formatted") or (
                f"{price['amount'] / 100:.2f} {price.get('currency', '')}".strip()
                if price.get("amount") is not None
                else None
            )
        if (group := queue.get("BOARDING_GROUP")) is not None:
            attrs["boarding_group_status"] = group.get("allocationStatus")
            attrs["boarding_group_current_start"] = group.get("currentGroupStart")
            attrs["boarding_group_current_end"] = group.get("currentGroupEnd")
            attrs["boarding_group_next_allocation"] = group.get("nextAllocationTime")
            attrs["boarding_group_estimated_wait"] = group.get("estimatedWait")

        now = dt_util.utcnow()
        starts: list[str] = []
        next_show: datetime | None = None
        for show in item.get("showtimes") or []:
            start = parse_api_datetime(show.get("startTime"), tz)
            if start is None:
                continue
            starts.append(start.isoformat())
            if start > now and (next_show is None or start < next_show):
                next_show = start
        attrs["showtimes"] = starts
        attrs["next_showtime"] = next_show.isoformat() if next_show else None
        return attrs


class ParkStatusSensor(CoordinatorEntity[ThemeParksScheduleCoordinator], SensorEntity):
    """Open/closed state and today's hours for one park."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_translation_key = "park_status"
    _attr_icon = "mdi:gate"
    _unrecorded_attributes = frozenset({"upcoming", "current_schedules", "timezone", "purchases"})

    def __init__(
        self, coordinator: ThemeParksScheduleCoordinator, flt: EntityFilter, park_id: str
    ) -> None:
        """Create the sensor."""
        super().__init__(coordinator)
        self._park_id = park_id
        self._attr_unique_id = f"{park_id}{STATUS_SUFFIX}"
        self._attr_device_info = flt.device_info(park_id)

    async def async_added_to_hass(self) -> None:
        """Recompute open/closed every minute between schedule refreshes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._tick, timedelta(minutes=1), name=f"{DOMAIN} park status"
            )
        )

    @callback
    def _tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    def _status(self) -> tuple[str, dict[str, Any]]:
        parks = self.coordinator.data.parks if self.coordinator.data else {}
        return park_status(parks.get(self._park_id), dt_util.utcnow())

    @property
    def native_value(self) -> str:
        """Open, Closed, Special Ticketed Event or Private Event."""
        return self._status()[0]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Today's hours and events, plus the days ahead."""
        attrs = self._status()[1]
        attrs["park_id"] = self._park_id
        return attrs
