"""Park hours calendars for ThemeParks.wiki."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import ThemeParksConfigEntry
from .const import ATTRIBUTION, SCHEDULE_INFO, SCHEDULE_LABELS, SCHEDULE_OPERATING
from .coordinator import ScheduleItem, ThemeParksScheduleCoordinator
from .entity import CALENDAR_SUFFIX, EntityFilter

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ThemeParksConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create one hours calendar per selected park."""
    data = entry.runtime_data
    flt = data.filter
    if not flt.calendars:
        return
    async_add_entities(
        ParkHoursCalendar(data.schedule, flt, park_id)
        for park_id in sorted(flt.selected_parks)
        if park_id in flt.park_names
    )


def _to_event(item: ScheduleItem, park_name: str) -> CalendarEvent:
    label = SCHEDULE_LABELS.get(item.type, item.type.replace("_", " ").title())
    if item.type == SCHEDULE_OPERATING:
        summary = f"{park_name} open"
        description = item.description or label
    else:
        summary = item.description or label
        description = label
    return CalendarEvent(
        start=item.opening,
        end=item.closing,
        summary=summary,
        description=description,
        location=park_name,
        uid=f"{item.type}-{item.opening.isoformat()}",
    )


class ParkHoursCalendar(CoordinatorEntity[ThemeParksScheduleCoordinator], CalendarEntity):
    """Opening hours, extra hours and ticketed events for one park."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_translation_key = "park_hours"
    _attr_icon = "mdi:calendar-clock"

    def __init__(
        self, coordinator: ThemeParksScheduleCoordinator, flt: EntityFilter, park_id: str
    ) -> None:
        """Create the calendar."""
        super().__init__(coordinator)
        self._flt = flt
        self._park_id = park_id
        self._attr_unique_id = f"{park_id}{CALENDAR_SUFFIX}"
        self._attr_device_info = flt.device_info(park_id)

    def _items(self) -> list[ScheduleItem]:
        if not self.coordinator.data:
            return []
        park = self.coordinator.data.parks.get(self._park_id)
        if park is None:
            return []
        # INFO entries (e.g. "Park Hopping") describe the day rather than
        # being events, so they stay on the status sensor only.
        return [i for i in park.items if i.type != SCHEDULE_INFO]

    @property
    def _park_name(self) -> str:
        return self._flt.park_names.get(self._park_id, self._park_id)

    @property
    def event(self) -> CalendarEvent | None:
        """The current event, or else the next one."""
        now = dt_util.utcnow()
        items = self._items()
        current = next((i for i in items if i.covers(now)), None)
        upcoming = next((i for i in items if i.opening > now), None)
        chosen = current or upcoming
        return _to_event(chosen, self._park_name) if chosen else None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Events overlapping the requested window."""
        return [
            _to_event(i, self._park_name)
            for i in self._items()
            if i.closing > start_date and i.opening < end_date
        ]
