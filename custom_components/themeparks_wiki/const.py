"""Constants for the ThemeParks.wiki integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "themeparks_wiki"

API_BASE_URL: Final = "https://api.themeparks.wiki/v1"
ATTRIBUTION: Final = "Powered by ThemeParks.wiki"
MANUFACTURER: Final = "ThemeParks.wiki"

# The domain of the older danielsmith-eu "Theme Parks" integration, whose
# entity IDs this integration can take over.
LEGACY_DOMAIN: Final = "themeparks"

# Config entry data
CONF_API_KEY: Final = "api_key"
CONF_DESTINATION_ID: Final = "destination_id"
CONF_DESTINATION_NAME: Final = "destination_name"
CONF_PARK_CATALOG: Final = "park_catalog"
CONF_LEGACY_ENTITIES: Final = "legacy_entities"
CONF_TAKE_OVER_LEGACY: Final = "take_over_legacy"

# Config entry options
CONF_PARKS: Final = "parks"
CONF_INCLUDE_SHOWS: Final = "include_shows"
CONF_INCLUDE_RESTAURANTS: Final = "include_restaurants"
CONF_INCLUDE_OTHER: Final = "include_other"
CONF_CALENDARS: Final = "calendars"
CONF_LIVE_INTERVAL: Final = "live_interval"
CONF_SCHEDULE_INTERVAL: Final = "schedule_interval"

DEFAULT_INCLUDE_SHOWS: Final = True
DEFAULT_INCLUDE_RESTAURANTS: Final = False
DEFAULT_INCLUDE_OTHER: Final = True
DEFAULT_CALENDARS: Final = True
# Seconds. The API caches live data for 60 seconds, so polling faster
# returns the same response.
DEFAULT_LIVE_INTERVAL: Final = 120
MIN_LIVE_INTERVAL: Final = 60
MAX_LIVE_INTERVAL: Final = 1800
# Minutes.
DEFAULT_SCHEDULE_INTERVAL: Final = 60
MIN_SCHEDULE_INTERVAL: Final = 15
MAX_SCHEDULE_INTERVAL: Final = 1440

# How often the park/land/attraction tree is re-read, in seconds. An unknown
# attraction in the live feed can ask for an early re-read, but not more
# often than TOPOLOGY_MIN_AGE.
TOPOLOGY_MAX_AGE: Final = 12 * 3600
TOPOLOGY_MIN_AGE: Final = 600

# Pseudo park key for entities that belong to the destination but to no park
# (for example Disney Springs at Walt Disney World).
OTHER_PARK: Final = "_other"

ENTITY_TYPE_ATTRACTION: Final = "ATTRACTION"
ENTITY_TYPE_SHOW: Final = "SHOW"
ENTITY_TYPE_RESTAURANT: Final = "RESTAURANT"
ENTITY_TYPE_PARK: Final = "PARK"
ENTITY_TYPE_DESTINATION: Final = "DESTINATION"

# Park status sensor states. These match the older integration's states so
# existing automations and intent scripts keep working.
STATUS_OPEN: Final = "Open"
STATUS_CLOSED: Final = "Closed"
STATUS_TICKETED_EVENT: Final = "Special Ticketed Event"
STATUS_PRIVATE_EVENT: Final = "Private Event"

SCHEDULE_OPERATING: Final = "OPERATING"
SCHEDULE_TICKETED_EVENT: Final = "TICKETED_EVENT"
SCHEDULE_PRIVATE_EVENT: Final = "PRIVATE_EVENT"
SCHEDULE_EXTRA_HOURS: Final = "EXTRA_HOURS"
SCHEDULE_INFO: Final = "INFO"

SCHEDULE_LABELS: Final = {
    SCHEDULE_OPERATING: "Park hours",
    SCHEDULE_TICKETED_EVENT: "Special ticketed event",
    SCHEDULE_PRIVATE_EVENT: "Private event",
    SCHEDULE_EXTRA_HOURS: "Extra hours",
    SCHEDULE_INFO: "Information",
}
