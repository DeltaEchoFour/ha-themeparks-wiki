"""Fixtures for ThemeParks.wiki tests."""

from __future__ import annotations

from typing import Any

import pytest

from custom_components.themeparks_wiki.const import API_BASE_URL

DEST = "e957da41-3552-4cf6-b636-5babc5cbc4e5"
MK = "75ea578a-adc8-4116-a54d-dccb60765ef9"
EP = "47f90d2c-e191-4239-a466-5892ef59a88b"
SPACE = "b2260923-9315-40fd-9c6b-44dd811dbe64"
HEA = "22b78ed9-a692-47cb-b6a4-6d1224ff67e3"
TEST_TRACK = "tt000000-0000-0000-0000-000000000001"
LEVEL99 = "e18743bb-86dd-4c4b-b7e5-e067c6d0cecc"
BOG = "rest0000-0000-0000-0000-000000000001"
TOMORROWLAND = "land0000-0000-0000-0000-000000000001"
SPRINGS = "area0000-0000-0000-0000-000000000001"
NEWRIDE = "new00000-0000-0000-0000-000000000001"
MYSTERY = "myst0000-0000-0000-0000-000000000001"

# Frozen "now" for every test: 12:00 Eastern on 2026-10-29.
NOW = "2026-10-29T16:00:00+00:00"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    """Load custom_components/ in every test."""


def destinations() -> dict[str, Any]:
    return {
        "destinations": [
            {
                "id": DEST,
                "name": "Walt Disney World® Resort",
                "slug": "waltdisneyworldresort",
                "parks": [
                    {"id": MK, "name": "Magic Kingdom Park"},
                    {"id": EP, "name": "EPCOT"},
                ],
            },
            {"id": "other-dest", "name": "Universal Orlando Resort", "parks": []},
        ]
    }


def children() -> dict[str, Any]:
    return {
        "id": DEST,
        "name": "Walt Disney World® Resort",
        "entityType": "DESTINATION",
        "timezone": "America/New_York",
        "children": [
            {"id": MK, "name": "Magic Kingdom Park", "entityType": "PARK", "parentId": DEST},
            {"id": EP, "name": "EPCOT", "entityType": "PARK", "parentId": DEST},
            {"id": TOMORROWLAND, "name": "Tomorrowland", "entityType": "ATTRACTION", "parentId": MK},
            {"id": SPACE, "name": "Space Mountain", "entityType": "ATTRACTION", "parentId": TOMORROWLAND},
            {"id": HEA, "name": "Happily Ever After", "entityType": "SHOW", "parentId": MK},
            {"id": BOG, "name": "Be Our Guest Restaurant", "entityType": "RESTAURANT", "parentId": MK},
            {"id": TEST_TRACK, "name": "Test Track", "entityType": "ATTRACTION", "parentId": EP},
            {"id": SPRINGS, "name": "Disney Springs", "entityType": "ATTRACTION", "parentId": DEST},
            {"id": LEVEL99, "name": "LEVEL99", "entityType": "ATTRACTION", "parentId": SPRINGS},
        ],
    }


def live() -> dict[str, Any]:
    return {
        "id": DEST,
        "name": "Walt Disney World® Resort",
        "entityType": "DESTINATION",
        "timezone": "America/New_York",
        "liveData": [
            {
                "id": SPACE,
                "name": "Space Mountain",
                "parkId": MK,
                "entityType": "ATTRACTION",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:58:00Z",
                "queue": {
                    "STANDBY": {"waitTime": 45},
                    "RETURN_TIME": {
                        "state": "AVAILABLE",
                        "returnStart": "2026-10-29T13:05:00-04:00",
                        "returnEnd": "2026-10-29T14:05:00-04:00",
                    },
                },
            },
            {
                "id": HEA,
                "name": "Happily Ever After",
                "entityType": "SHOW",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:00:00Z",
                "showtimes": [
                    {"type": "Performance Time", "startTime": "2026-10-29T21:00:00-04:00", "endTime": "2026-10-29T21:20:00-04:00"},
                    {"type": "Performance Time", "startTime": "2026-10-28T21:00:00-04:00", "endTime": "2026-10-28T21:20:00-04:00"},
                ],
            },
            {
                "id": TEST_TRACK,
                "name": "Test Track",
                "entityType": "ATTRACTION",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:58:00Z",
                "queue": {
                    "STANDBY": {"waitTime": 55},
                    "SINGLE_RIDER": {"waitTime": 20},
                    "PAID_RETURN_TIME": {
                        "state": "AVAILABLE",
                        "returnStart": "2026-10-29T15:00:00-04:00",
                        "returnEnd": None,
                        "price": {"amount": 2500, "currency": "USD", "formatted": "$25.00"},
                    },
                },
            },
            {
                "id": LEVEL99,
                "name": "LEVEL99",
                "parkId": None,
                "entityType": "ATTRACTION",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:58:00Z",
                "queue": {"STANDBY": {"waitTime": 0}},
            },
            {
                "id": BOG,
                "name": "Be Our Guest Restaurant",
                "entityType": "RESTAURANT",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:58:00Z",
            },
            {
                "id": NEWRIDE,
                "name": "Brand New Ride",
                "parkId": MK,
                "entityType": "ATTRACTION",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:58:00Z",
                "queue": {"STANDBY": {"waitTime": 5}},
            },
            {
                "id": MYSTERY,
                "name": "Mystery Ride",
                "entityType": "ATTRACTION",
                "status": "OPERATING",
                "lastUpdated": "2026-10-29T15:58:00Z",
                "queue": {"STANDBY": {"waitTime": 15}},
            },
        ],
    }


def schedule() -> dict[str, Any]:
    return {
        "id": DEST,
        "name": "Walt Disney World® Resort",
        "entityType": "DESTINATION",
        "timezone": "America/New_York",
        "parks": [
            {
                "id": MK,
                "name": "Magic Kingdom Park",
                "timezone": None,
                "schedule": [
                    {"date": "2026-10-29", "type": "TICKETED_EVENT", "description": "Early Entry",
                     "openingTime": "2026-10-29T07:30:00-04:00", "closingTime": "2026-10-29T08:00:00-04:00"},
                    {"date": "2026-10-29", "type": "OPERATING",
                     "openingTime": "2026-10-29T08:00:00-04:00", "closingTime": "2026-10-29T18:00:00-04:00",
                     "purchases": [
                         {"id": "lightninglane_1", "name": "Lightning Lane for TRON Lightcycle / Run", "type": "ATTRACTION",
                          "price": {"amount": 2200, "currency": "USD", "formatted": "$22.00"}, "available": False},
                         {"id": "llmp_1", "name": "Lightning Lane Multi Pass", "type": "PACKAGE",
                          "price": {"amount": 3200, "currency": "USD"}, "available": True},
                     ]},
                    {"date": "2026-10-29", "type": "INFO", "description": "Park Hopping",
                     "openingTime": "2026-10-29T08:00:00-04:00", "closingTime": "2026-10-29T18:00:00-04:00"},
                    {"date": "2026-10-29", "type": "TICKETED_EVENT",
                     "description": "Mickey's Not-So-Scary Halloween Party",
                     "openingTime": "2026-10-29T19:00:00-04:00", "closingTime": "2026-10-30T00:00:00-04:00"},
                    {"date": "2026-10-30", "type": "OPERATING",
                     "openingTime": "2026-10-30T09:00:00-04:00", "closingTime": "2026-10-30T22:00:00-04:00"},
                ],
            },
            {
                "id": EP,
                "name": "EPCOT",
                "timezone": "America/New_York",
                "schedule": [
                    {"date": "2026-10-29", "type": "OPERATING",
                     "openingTime": "2026-10-29T09:00:00", "closingTime": "2026-10-29T21:00:00"},
                ],
            },
        ],
    }


def mock_api(aioclient_mock: Any, *, live_status: int = 200, dest_status: int = 200) -> None:
    """Register every endpoint the integration calls."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API_BASE_URL}/destinations", json=destinations(), status=dest_status)
    aioclient_mock.get(f"{API_BASE_URL}/entity/{DEST}/children", json=children())
    aioclient_mock.get(f"{API_BASE_URL}/entity/{DEST}/live", json=live(), status=live_status)
    aioclient_mock.get(f"{API_BASE_URL}/entity/{DEST}/schedule", json=schedule())
