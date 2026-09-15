import asyncio
import json
from datetime import date, datetime, timezone
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from .. import views_api
from ..bitcoin_history import events_on, history_screen, load_events
from ..colour_rendering import render_colour_screen
from ..image_cache import ImageCache
from ..rendering import render_screen
from .asgi import asgi_transport


def test_calendar_import_and_anniversaries():
    assert len(load_events()) == 219
    assert events_on(date(2026, 8, 15)) == events_on(date(2030, 8, 15))
    assert any(e["title"] == "RPOW Launched" for e in events_on(date(2030, 8, 15)))
    assert all("<br" not in e["description"] for e in load_events())


def test_history_renders_both_devices():
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    data = history_screen(events_on(now.date()), now, 30)
    for png, size in [
        (render_screen(data, "bitcoin_history", "12:34"), (960, 540)),
        (render_colour_screen(data, "bitcoin_history", "12:34"), (480, 320)),
    ]:
        assert Image.open(BytesIO(png)).size == size


@pytest.mark.parametrize(
    "has_event,enabled,requested,expected,next_page",
    [
        (False, True, 1, 2, 0),
        (False, True, 0, 0, 2),
        (True, True, 1, 1, 2),
        (True, False, 1, 1, 0),
    ],
)
def test_rotation(monkeypatch, has_event, enabled, requested, expected, next_page):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 12, 23, 30, tzinfo=timezone.utc)

    async def get_gerty(_):
        return SimpleNamespace(
            display_preferences=json.dumps(
                {"quote": True, "bitcoin_history": enabled, "dashboard": True}
            ),
            utc_offset=2,
            refresh_time=30,
            json=lambda: "history-test",
        )

    seen = []

    def events(day):
        seen.append(day)
        return (
            [{"title": "Anniversary", "description": "Bitcoin history."}]
            if has_event
            else []
        )

    async def get_data(*args):
        return {"title": "Other screen", "areas": []}

    monkeypatch.setattr(views_api, "datetime", Clock)
    monkeypatch.setattr(views_api, "get_gerty", get_gerty)
    monkeypatch.setattr(views_api, "events_on", events)
    monkeypatch.setattr(views_api, "get_screen_data", get_data)
    monkeypatch.setattr(views_api, "gerty_should_sleep", lambda _: False)
    monkeypatch.setattr(views_api, "image_cache", ImageCache())
    app = FastAPI()
    app.include_router(views_api.gerty_api_router)

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/v1/gerty/pages/test/{requested}")
            assert response.status_code == 200
            assert response.json()["page"] == expected
            assert response.json()["next_page"] == next_page

    asyncio.run(check())
    assert seen == ([date(2026, 9, 13)] if enabled else [])
