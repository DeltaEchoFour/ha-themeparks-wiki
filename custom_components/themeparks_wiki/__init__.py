"""The ThemeParks.wiki integration."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ThemeParksClient
from .const import (
    CONF_API_KEY,
    CONF_CALENDARS,
    CONF_DESTINATION_ID,
    CONF_LEGACY_ENTITIES,
    DEFAULT_CALENDARS,
    DOMAIN,
)
from .coordinator import ThemeParksLiveCoordinator, ThemeParksScheduleCoordinator
from .entity import EntityFilter

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]


@dataclass(slots=True)
class ThemeParksRuntimeData:
    """Objects shared by this entry's platforms."""

    client: ThemeParksClient
    live: ThemeParksLiveCoordinator
    schedule: ThemeParksScheduleCoordinator
    filter: EntityFilter


type ThemeParksConfigEntry = ConfigEntry[ThemeParksRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: ThemeParksConfigEntry) -> bool:
    """Set up ThemeParks.wiki from a config entry."""
    client = ThemeParksClient(
        async_get_clientsession(hass), entry.data.get(CONF_API_KEY) or None
    )
    schedule = ThemeParksScheduleCoordinator(hass, entry, client)
    live = ThemeParksLiveCoordinator(hass, entry, client)
    # The park tree comes with the schedule refresh and is needed to file
    # live entities under the right park, so it goes first.
    await schedule.async_config_entry_first_refresh()
    await live.async_config_entry_first_refresh()

    entity_filter = EntityFilter(entry, schedule)
    entry.runtime_data = ThemeParksRuntimeData(client, live, schedule, entity_filter)

    # Park devices point at the destination device, so it must exist first.
    dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        **entity_filter.device_info(entry.data[CONF_DESTINATION_ID]),
    )

    _async_adopt_legacy_entities(hass, entry, entity_filter)
    _async_remove_excluded(hass, entry, entity_filter)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ThemeParksConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ThemeParksConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a park device from the UI; it returns if still selected."""
    return True


def _async_adopt_legacy_entities(
    hass: HomeAssistant, entry: ThemeParksConfigEntry, entity_filter: EntityFilter
) -> None:
    """Give new entities the entity IDs the old integration used.

    The config flow recorded the old entity IDs (keyed by the same unique IDs
    this integration uses) and removed the old integration, which freed those
    IDs. Registering our entities first with that object ID makes Home
    Assistant reuse it, so history, dashboards and automations carry over.
    This runs once; the record is dropped afterwards.
    """
    legacy: dict[str, dict[str, Any]] = entry.data.get(CONF_LEGACY_ENTITIES) or {}
    if not legacy:
        return
    ent_reg = er.async_get(hass)
    adopted = 0
    for unique_id, info in legacy.items():
        if not entity_filter.allows_unique_id(unique_id, Platform.SENSOR, strict=True):
            continue
        if ent_reg.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id):
            continue
        old_entity_id: str = info.get("entity_id", "")
        if not old_entity_id.startswith("sensor.") or ent_reg.async_get(old_entity_id):
            continue
        # A leftover state from the removed integration (for example a
        # restored "unavailable") would make Home Assistant pick "<id>_2".
        if hass.states.get(old_entity_id) is not None:
            hass.states.async_remove(old_entity_id)
        entity = ent_reg.async_get_or_create(
            Platform.SENSOR,
            DOMAIN,
            unique_id,
            suggested_object_id=old_entity_id.split(".", 1)[1],
            config_entry=entry,
        )
        updates: dict[str, Any] = {}
        for key in ("name", "icon", "area_id"):
            if info.get(key):
                updates[key] = info[key]
        if info.get("labels"):
            updates["labels"] = set(info["labels"])
        if info.get("aliases"):
            updates["aliases"] = info["aliases"]
        if updates:
            try:
                ent_reg.async_update_entity(entity.entity_id, **updates)
            except (TypeError, ValueError) as err:
                _LOGGER.debug("Could not copy settings to %s: %s", entity.entity_id, err)
        expose = info.get("should_expose")
        if expose is not None:
            ent_reg.async_update_entity_options(
                entity.entity_id, "conversation", {"should_expose": bool(expose)}
            )
        adopted += 1
    _LOGGER.info("Took over %s entity IDs from the old Theme Parks integration", adopted)
    data = {k: v for k, v in entry.data.items() if k != CONF_LEGACY_ENTITIES}
    hass.config_entries.async_update_entry(entry, data=data)


def _async_remove_excluded(
    hass: HomeAssistant, entry: ThemeParksConfigEntry, entity_filter: EntityFilter
) -> None:
    """Drop entities and devices for parks or types that were deselected."""
    ent_reg = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if not entity_filter.allows_unique_id(reg_entry.unique_id, reg_entry.domain):
            ent_reg.async_remove(reg_entry.entity_id)
    if not entry.options.get(CONF_CALENDARS, DEFAULT_CALENDARS):
        for reg_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if reg_entry.domain == Platform.CALENDAR:
                ent_reg.async_remove(reg_entry.entity_id)

    dev_reg = dr.async_get(hass)
    keep = entity_filter.device_ids()
    for device in dr.async_entries_for_config_entry(dev_reg, entry.entry_id):
        ids = {i[1] for i in device.identifiers if i[0] == DOMAIN}
        if ids and not ids & keep:
            dev_reg.async_update_device(device.id, remove_config_entry_id=entry.entry_id)
