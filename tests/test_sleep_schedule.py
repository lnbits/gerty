"""Schedule boundaries and device API sleep responses."""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from ..sleep_schedule import local_time, sleep_data, validate_schedule
from .asgi import asgi_transport


def device(**schedule):
    return SimpleNamespace(
        utc_offset=0,
        display_preferences=json.dumps(
            {
                "dashboard": True,
                "_schedule": {
                    "enabled": True,
                    "timezone": "Europe/London",
                    "sleep_time": "22:00",
                    "wake_time": "06:00",
                    **schedule,
                },
            }
        ),
    )


@pytest.mark.parametrize(
    "instant,seconds",
    [
        ("2026-01-01T21:59:00+00:00", None),
        ("2026-01-01T22:00:00+00:00", 28800),
        ("2026-01-02T05:59:00+00:00", 60),
        ("2026-01-02T06:00:00+00:00", None),
        ("2026-03-28T22:00:00+00:00", 25200),
        ("2026-10-24T21:00:00+00:00", 32400),
    ],
)
def test_overnight_and_dst(instant, seconds):
    data = sleep_data(device(), datetime.fromisoformat(instant))
    if seconds is None:
        assert data is None
    else:
        assert data is not None
        assert data["sleep_seconds"] == seconds
        assert "deep_sleep" not in data
        assert "display_off" not in data


def test_daytime_disabled_and_fractional_timezone():
    now = datetime.fromisoformat("2026-01-01T12:00:00+00:00")
    assert sleep_data(device(enabled=False), now) is None
    data = sleep_data(device(sleep_time="11:00", wake_time="13:00"), now)
    assert data is not None
    assert data["sleep_seconds"] == 3600
    assert local_time(device(timezone="Asia/Kolkata"), now).strftime("%H:%M") == "17:30"


@pytest.mark.parametrize(
    "schedule",
    [
        {"timezone": "invalid"},
        {"sleep_time": "25:00"},
        {"wake_time": "6:00"},
        {"enabled": "true"},
        {"enabled": True, "sleep_time": "06:00", "wake_time": "06:00"},
    ],
)
def test_validation(schedule):
    with pytest.raises(ValueError):
        validate_schedule({"_schedule": schedule})


def test_all_device_routes_sleep_without_fetching(monkeypatch):
    from .. import views_api
    from ..image_cache import ImageCache

    gerty = device()
    preferences = json.loads(gerty.display_preferences)
    preferences["_display"] = {"profile": "colour_240x240"}
    gerty.display_preferences = json.dumps(preferences)

    async def get_gerty(_):
        return gerty

    async def unexpected(*args):
        pytest.fail("Sleeping devices must not fetch screen or mempool data")

    monkeypatch.setattr(views_api, "get_gerty", get_gerty)
    monkeypatch.setattr(views_api, "get_screen_data", unexpected)
    monkeypatch.setattr(views_api, "get_mempool_info", unexpected)
    monkeypatch.setattr(
        views_api,
        "sleep_data",
        lambda g: sleep_data(g, datetime.fromisoformat("2026-01-01T23:00:00+00:00")),
    )
    cache = ImageCache()
    revision = cache.put("test:0", b"png", 300).revision
    monkeypatch.setattr(views_api, "image_cache", cache)
    app = FastAPI()
    app.include_router(views_api.gerty_api_router)

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            paths = [
                "pages/test",
                "pages/test/0",
                f"images/{revision}.png",
                "satoshiquote?gerty_id=test",
            ]
            paths += [
                f"{endpoint}/test"
                for endpoint in [
                    "fees-recommended",
                    "hashrate-1w",
                    "hashrate-1m",
                    "statistics",
                    "difficulty-adjustment",
                    "tip-height",
                    "mempool",
                ]
            ]
            for path in paths:
                response = await client.get(f"/api/v1/gerty/{path}")
                assert response.status_code == 200
                data = response.json()
                assert data["sleep_mode"] is True
                assert "display_off" not in data
                assert "deep_sleep" not in data
                assert data["sleep_seconds"] == 25200
                assert set(data) == {
                    "schema_version",
                    "sleep_mode",
                    "sleep_seconds",
                    "wake_at",
                }
                assert response.headers["cache-control"] == "no-store"

            async def preview_data(*args):
                return {"title": "Preview", "areas": []}

            gerty.refresh_time = 300
            gerty.json = lambda: "sleep-preview-test"
            monkeypatch.setattr(views_api, "get_screen_data", preview_data)
            response = await client.get("/api/v1/gerty/pages/test/0?preview=true")
            assert response.status_code == 200
            manifest = response.json()
            assert manifest["sleep_mode"] is False
            assert manifest["refresh_seconds"] == 300
            assert manifest["image_url"].endswith("?preview=true")
            image = await client.get(manifest["image_url"])
            assert image.headers["content-type"] == "image/png"
            assert image.content.startswith(b"\x89PNG")
            # A preview snapshot must still respect sleep on the device URL.
            image = await client.get(manifest["image_url"].split("?")[0])
            assert image.json()["sleep_mode"] is True
            response = await client.get("/api/v1/gerty/pages/test/0?preview=false")
            assert response.json()["sleep_mode"] is True

    asyncio.run(check())
