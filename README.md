# ThemeParks.wiki for Home Assistant

Live wait times, park hours, ticketed events and showtimes for any resort covered by
[ThemeParks.wiki](https://www.themeparks.wiki), set up entirely from the Home Assistant UI.

Powered by ThemeParks.wiki.

## What you get

For each resort you add, one device per park plus one for the resort itself:

| Entity | State | Notable attributes |
|---|---|---|
| `sensor.<park>_<attraction>` | Posted standby wait, minutes | `attraction_name`, `park_name`, `park_id`, `status` (`OPERATING`, `DOWN`, `CLOSED`, `REFURBISHMENT`), `single_rider_wait`, `return_time_*` (free return times), `paid_return_time_*` incl. price, `boarding_group_*`, `showtimes`, `next_showtime`, `last_updated` |
| `sensor.<park>_status` | `Open`, `Closed`, `Special Ticketed Event` or `Private Event`, recomputed every minute | `opening_time`, `closing_time`, `schedule_type`, `all_schedules` (today: Early Entry, extra hours, parties, info), `next_opening_time`, `purchases` (today's paid line-skipping options and prices), `upcoming` (next 30 days, not recorded) |
| `calendar.<park>_hours` | On while the park or an event is open | Events for opening hours, extra hours and ticketed or private events for the next 30 days |

Attractions that belong to the resort but to no park (Disney Springs at Walt Disney World,
for example) sit on the resort device. New attractions appear automatically.

The whole resort is read in one request per interval, so the default settings use
well under 1% of the free rate limit.

## Install

1. In HACS, open the menu, choose **Custom repositories**, add
   `https://github.com/DeltaEchoFour/ha-themeparks-wiki` with type **Integration**, and
   download **ThemeParks.wiki**.
2. Restart Home Assistant.
3. **Settings > Devices & services > Add integration > ThemeParks.wiki.**

Without HACS, copy `custom_components/themeparks_wiki` into your config's
`custom_components` folder and restart.

## Setup

1. **API key (optional).** Leave it empty to use the API anonymously, limited per IP
   address. A key from [themeparks.wiki/api](https://www.themeparks.wiki/api) raises the
   limit.
2. **Resort.** One entry per resort; add the integration again for another resort.
3. **Parks.** Choose which of the resort's parks to track.
4. **Take over the old Theme Parks integration** (only shown if it is installed). The new
   entities take the old entity IDs, names, areas, labels, aliases and voice exposure, so
   history, dashboards, automations and intent scripts keep working. The old integration's
   entry is removed to free the IDs; uninstall it from HACS afterwards.

## Change settings later

- **Configure** (options): parks, shows, restaurants, areas outside the parks, park hours
  calendars, live update interval (60–1800 s, default 120 s) and park hours interval
  (15–1440 min, default 60 min). Saving reloads the integration and removes entities for
  anything you turned off.
- **Reconfigure**: replace the API key, or remove it to go keyless.
- If the API rejects the key, Home Assistant asks for a new one (reauthentication).

## Notes

- ThemeParks.wiki caches live data for 60 seconds; a shorter interval only repeats data.
- A missing wait means the API reported none (for example, a show or a closed ride), so
  the sensor is `unknown` rather than `0`.
- The API's terms ask for a visible "Powered by ThemeParks.wiki" credit wherever the data
  is displayed. Every entity carries it as its attribution.
