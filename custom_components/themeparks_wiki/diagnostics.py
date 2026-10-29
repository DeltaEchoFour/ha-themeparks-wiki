"""Diagnostics for ThemeParks.wiki."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import ThemeParksConfigEntry
from .const import CONF_API_KEY

TO_REDACT = {CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ThemeParksConfigEntry
) -> dict[str, Any]:
    """Return entry settings and a summary of the latest data."""
    data = entry.runtime_data
    schedule = data.schedule.data
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "live": {
            "last_update_success": data.live.last_update_success,
            "entities": len(data.live.data or {}),
            "timezone": str(data.live.timezone),
        },
        "schedule": {
            "last_update_success": data.schedule.last_update_success,
            "parks": {
                pid: {"timezone": str(p.timezone), "entries": len(p.items)}
                for pid, p in (schedule.parks.items() if schedule else [])
            },
            "park_names": schedule.park_names if schedule else {},
            "topology_entities": len(schedule.topology) if schedule else 0,
        },
        "selected_parks": sorted(data.filter.selected_parks),
        "entity_types": sorted(data.filter.types),
    }
