"""End-to-end tests for ThemeParks.wiki against a real Home Assistant core."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.themeparks_wiki.const import (
    CONF_API_KEY,
    CONF_CALENDARS,
    CONF_PARKS,
    DOMAIN,
    LEGACY_DOMAIN,
)

from .conftest import (
    BOG,
    DEST,
    EP,
    HEA,
    LEVEL99,
    MK,
    MYSTERY,
    NOW,
    SPACE,
    TEST_TRACK,
    mock_api,
)


@pytest.fixture(autouse=True)
def _frozen(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


async def _run_flow(hass: HomeAssistant, parks: list[str] | None = None, api_key: str = "") -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: api_key})
    assert result["step_id"] == "destination"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"destination": DEST})
    assert result["step_id"] == "parks"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PARKS: parks or [MK, EP]}
    )


async def test_full_setup(hass: HomeAssistant, aioclient_mock) -> None:
    """Flow creates the entry and every expected entity."""
    mock_api(aioclient_mock)
    result = await _run_flow(hass)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Walt Disney World® Resort"
    await hass.async_block_till_done()

    space = hass.states.get("sensor.magic_kingdom_park_space_mountain")
    assert space is not None
    assert space.state == "45"
    assert space.attributes["unit_of_measurement"] == "min"
    assert space.attributes["park_name"] == "Magic Kingdom Park"
    assert space.attributes["attraction_name"] == "Space Mountain"
    assert space.attributes["status"] == "OPERATING"
    assert space.attributes["return_time_state"] == "AVAILABLE"
    assert space.attributes["attribution"] == "Powered by ThemeParks.wiki"

    track = hass.states.get("sensor.epcot_test_track")
    assert track.state == "55"
    assert track.attributes["single_rider_wait"] == 20
    assert track.attributes["paid_return_time_price"] == "$25.00"

    show = hass.states.get("sensor.magic_kingdom_park_happily_ever_after")
    assert show.state == "unknown"
    assert show.attributes["next_showtime"] == "2026-10-29T21:00:00-04:00"
    assert len(show.attributes["showtimes"]) == 2

    # Outside any park: filed under the resort device.
    level99 = hass.states.get("sensor.walt_disney_world_r_resort_level99")
    assert level99 is not None and level99.state == "0"
    assert level99.attributes["park_id"] is None

    # Restaurants are off by default. A ride missing from the park tree is
    # placed by its live parkId; one with neither waits for a tree refresh.
    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, BOG) is None
    new_ride = hass.states.get("sensor.magic_kingdom_park_brand_new_ride")
    assert new_ride is not None and new_ride.state == "5"
    assert new_ride.attributes["park_name"] == "Magic Kingdom Park"
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, MYSTERY) is None

    status = hass.states.get("sensor.magic_kingdom_park_status")
    assert status.state == "Open"
    assert status.attributes["opening_time"] == "2026-10-29T08:00:00-04:00"
    assert status.attributes["closing_time"] == "2026-10-29T18:00:00-04:00"
    assert status.attributes["schedule_type"] == "OPERATING"
    names = [s["name"] for s in status.attributes["all_schedules"]]
    assert names == ["Early Entry", None, "Park Hopping", "Mickey's Not-So-Scary Halloween Party"]
    assert status.attributes["next_opening_time"] == "2026-10-30T09:00:00-04:00"
    assert status.attributes["timezone"] == "America/New_York"
    assert status.attributes["purchases"] == [
        {"name": "Lightning Lane for TRON Lightcycle / Run", "type": "ATTRACTION", "price": "$22.00", "available": False},
        {"name": "Lightning Lane Multi Pass", "type": "PACKAGE", "price": "32.00 USD", "available": True},
    ]

    # Naive EPCOT times are read in the park's timezone.
    epcot = hass.states.get("sensor.epcot_status")
    assert epcot.state == "Open"
    assert epcot.attributes["closing_time"] == "2026-10-29T21:00:00-04:00"

    cal = hass.states.get("calendar.magic_kingdom_park_hours")
    assert cal is not None
    assert cal.state == "on"
    assert cal.attributes["message"] == "Magic Kingdom Park open"

    dev_reg = dr.async_get(hass)
    mk_device = dev_reg.async_get_device(identifiers={(DOMAIN, MK)})
    dest_device = dev_reg.async_get_device(identifiers={(DOMAIN, DEST)})
    assert mk_device.via_device_id == dest_device.id


async def test_status_follows_the_clock(hass: HomeAssistant, aioclient_mock, freezer) -> None:
    """The status sensor changes at closing time without a new API call."""
    mock_api(aioclient_mock)
    await _run_flow(hass)
    await hass.async_block_till_done()
    calls = aioclient_mock.call_count

    freezer.move_to("2026-10-30T00:00:00+00:00")  # 20:00 Eastern, party night
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.magic_kingdom_park_status").state == "Special Ticketed Event"

    freezer.move_to("2026-10-30T05:00:00+00:00")  # 01:00 Eastern
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.magic_kingdom_park_status").state == "Closed"
    # The minute ticks recompute locally; only scheduled polls hit the API.
    assert aioclient_mock.call_count >= calls


async def test_calendar_events(hass: HomeAssistant, aioclient_mock, hass_client) -> None:
    """The calendar lists hours and events but not INFO entries."""
    mock_api(aioclient_mock)
    await _run_flow(hass)
    await hass.async_block_till_done()
    events = await hass.services.async_call(
        "calendar",
        "get_events",
        {"entity_id": "calendar.magic_kingdom_park_hours", "duration": {"days": 3}, "start_date_time": "2026-10-29T00:00:00-04:00"},
        blocking=True,
        return_response=True,
    )
    summaries = [e["summary"] for e in events["calendar.magic_kingdom_park_hours"]["events"]]
    assert summaries == [
        "Early Entry",
        "Magic Kingdom Park open",
        "Mickey's Not-So-Scary Halloween Party",
        "Magic Kingdom Park open",
    ]


async def test_invalid_api_key(hass: HomeAssistant, aioclient_mock) -> None:
    """A rejected key shows an error on the first step."""
    mock_api(aioclient_mock, dest_status=401)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "bad"})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_api_key_header(hass: HomeAssistant, aioclient_mock) -> None:
    """The key is sent as x-api-key on every request."""
    mock_api(aioclient_mock)
    await _run_flow(hass, api_key="secret-key")
    await hass.async_block_till_done()
    headers = [call[3] for call in aioclient_mock.mock_calls]
    assert headers and all(h.get("x-api-key") == "secret-key" for h in headers)


async def test_duplicate_destination(hass: HomeAssistant, aioclient_mock) -> None:
    """A resort can only be added once."""
    mock_api(aioclient_mock)
    await _run_flow(hass)
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: ""})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"destination": DEST})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_take_over_legacy_ids(hass: HomeAssistant, aioclient_mock) -> None:
    """Old entity IDs, aliases and voice exposure move to the new entities."""
    legacy = MockConfigEntry(domain=LEGACY_DOMAIN, entry_id="01KCHW8FDJDXVVFJDCCR9GV49Q", title="Theme Park: Walt Disney World® Resort")
    legacy.add_to_hass(hass)
    ent_reg = er.async_get(hass)
    old_ride = ent_reg.async_get_or_create(
        "sensor", LEGACY_DOMAIN, f"{legacy.entry_id}_{SPACE}",
        suggested_object_id="space_mountain_walt_disney_world_r_resort", config_entry=legacy,
    )
    ent_reg.async_update_entity(old_ride.entity_id, aliases=["space mountain"])
    ent_reg.async_update_entity_options(old_ride.entity_id, "conversation", {"should_expose": False})
    old_status = ent_reg.async_get_or_create(
        "sensor", LEGACY_DOMAIN, f"{legacy.entry_id}_{MK}_status",
        suggested_object_id="magic_kingdom_park_status", config_entry=legacy,
    )
    ent_reg.async_update_entity_options(old_status.entity_id, "conversation", {"should_expose": True})
    # Something the new integration will never create.
    ent_reg.async_get_or_create("sensor", LEGACY_DOMAIN, f"{legacy.entry_id}_gone-ride", config_entry=legacy)
    # Like the real install: the old status sensors linger as restored states.
    hass.states.async_set("sensor.magic_kingdom_park_status", "unavailable", {"restored": True})
    hass.states.async_set("sensor.space_mountain_walt_disney_world_r_resort", "10", {"unit_of_measurement": "min"})

    mock_api(aioclient_mock)
    result = await _run_flow(hass)
    assert result["type"] is FlowResultType.FORM and result["step_id"] == "legacy"
    assert result["description_placeholders"]["count"] == "2"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"take_over_legacy": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(legacy.entry_id) is None
    ride = ent_reg.async_get("sensor.space_mountain_walt_disney_world_r_resort")
    assert ride is not None and ride.platform == DOMAIN and ride.unique_id == SPACE
    assert "space mountain" in ride.aliases
    assert ride.options["conversation"]["should_expose"] is False
    assert hass.states.get("sensor.space_mountain_walt_disney_world_r_resort").state == "45"

    status = ent_reg.async_get("sensor.magic_kingdom_park_status")
    assert status.platform == DOMAIN
    assert status.options["conversation"]["should_expose"] is True
    assert hass.states.get("sensor.magic_kingdom_park_status").state == "Open"

    # Rides the old integration never had still get the clean naming.
    assert hass.states.get("sensor.epcot_test_track") is not None
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert "legacy_entities" not in entry.data


async def test_decline_legacy(hass: HomeAssistant, aioclient_mock) -> None:
    """Declining keeps the old integration and uses fresh IDs."""
    legacy = MockConfigEntry(domain=LEGACY_DOMAIN, entry_id="legacy1")
    legacy.add_to_hass(hass)
    er.async_get(hass).async_get_or_create("sensor", LEGACY_DOMAIN, f"legacy1_{SPACE}", config_entry=legacy)
    mock_api(aioclient_mock)
    result = await _run_flow(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"take_over_legacy": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert hass.config_entries.async_get_entry("legacy1") is not None
    assert hass.states.get("sensor.magic_kingdom_park_space_mountain").state == "45"


async def test_options_remove_park_and_calendars(hass: HomeAssistant, aioclient_mock) -> None:
    """Deselecting a park and calendars removes their entities and device."""
    mock_api(aioclient_mock)
    await _run_flow(hass)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PARKS: [MK],
            "include_shows": False,
            "include_restaurants": True,
            "include_other": False,
            CONF_CALENDARS: False,
            "live_interval": 300,
            "schedule_interval": 120,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    ent_reg = er.async_get(hass)
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, TEST_TRACK) is None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, f"{EP}_status") is None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, HEA) is None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, LEVEL99) is None
    assert ent_reg.async_get_entity_id("calendar", DOMAIN, f"{MK}_calendar") is None
    assert ent_reg.async_get_entity_id("sensor", DOMAIN, BOG) is not None
    assert hass.states.get("sensor.magic_kingdom_park_space_mountain").state == "45"
    assert dr.async_get(hass).async_get_device(identifiers={(DOMAIN, EP)}) is None
    assert entry.runtime_data.live.update_interval == timedelta(seconds=300)


async def test_reconfigure_api_key(hass: HomeAssistant, aioclient_mock) -> None:
    """The key can be replaced and removed from the UI."""
    mock_api(aioclient_mock)
    await _run_flow(hass)
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_API_KEY: "new-key"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert entry.data[CONF_API_KEY] == "new-key"

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"remove_api_key": True})
    await hass.async_block_till_done()
    assert entry.data[CONF_API_KEY] == ""


async def test_rejected_key_starts_reauth(hass: HomeAssistant, aioclient_mock, freezer) -> None:
    """A 401 during polling asks the user for a new key."""
    mock_api(aioclient_mock)
    await _run_flow(hass, api_key="old")
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    mock_api(aioclient_mock, live_status=401)
    freezer.tick(timedelta(minutes=3))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    flows = [f for f in hass.config_entries.flow.async_progress() if f["context"]["source"] == "reauth"]
    assert flows and flows[0]["step_id"] == "reauth_confirm"

    mock_api(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(flows[0]["flow_id"], {CONF_API_KEY: "fresh"})
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "fresh"


async def test_diagnostics_redact_key(hass: HomeAssistant, aioclient_mock) -> None:
    """Diagnostics never include the key."""
    from custom_components.themeparks_wiki.diagnostics import async_get_config_entry_diagnostics

    mock_api(aioclient_mock)
    await _run_flow(hass, api_key="secret-key")
    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "secret-key" not in str(diag)
    assert diag["live"]["entities"] == 7
