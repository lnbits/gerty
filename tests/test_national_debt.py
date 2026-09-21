import asyncio
import json
from datetime import date
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from .. import national_debt as debt
from .. import views_api
from ..display_settings import DISPLAY_PROFILES
from ..image_cache import ImageCache
from .asgi import asgi_transport


def sample():
    return {
        **debt.daily_stats(
            [
                (date(2026, 8, 14), Decimal("39000000000000")),
                (date(2026, 9, 15), Decimal("40100000000000")),
                (date(2026, 9, 16), Decimal("40000000000000")),
            ]
        ),
        "nominal": [(date(1971, 1, 1), 391668), (date(2026, 1, 1), 39065421)],
        "ratio": [(date(1971, 1, 1), 34.5), (date(2026, 1, 1), 122.6)],
    }


def test_daily_dates_and_exact_negative_change():
    data = sample()
    assert data["recent"] == [
        (date(2026, 9, 16), Decimal("40000000000000"), Decimal("-100000000000")),
        (date(2026, 9, 15), Decimal("40100000000000"), Decimal("1100000000000")),
    ]
    assert data["daily_change"] == Decimal("-100000000000")
    assert data["month_change"] == Decimal("1000000000000")
    assert data["baseline_date"] == date(2026, 8, 14)
    assert debt.daily_stats([]) == {}
    assert debt.daily_stats([(date(2026, 1, 1), Decimal("1"))])["month_change"] is None
    assert debt.money(Decimal("-736959640.47"), signed=True) == "-$736.96M"


def test_source_parsing():
    points = debt.parse_daily(
        {
            "data": [
                {
                    "record_date": "2026-09-17",
                    "tot_pub_debt_out_amt": "40093343468150.50",
                },
                {
                    "record_date": "2026-09-16",
                    "tot_pub_debt_out_amt": "40094080427790.97",
                },
            ]
        }
    )
    assert debt.daily_stats(points)["daily_change"] == Decimal("-736959640.47")
    csv = (
        "observation_date,GFDEBTN\n1970-01-01,1\n1971-01-01,391668\n"
        "1971-04-01,.\n1971-07-01,412268\n"
    )
    assert debt.parse_history(csv, "GFDEBTN") == [
        (date(1971, 1, 1), 391668),
        (date(1971, 7, 1), 412268),
    ]
    for value in ("NaN", "Infinity", "-1"):
        with pytest.raises(ValueError):
            debt.parse_daily(
                {"data": [{"record_date": "2026-01-01", "tot_pub_debt_out_amt": value}]}
            )
    with pytest.raises(ValueError):
        debt.parse_history("observation_date,GFDEBTN\n1971-01-01,.\n", "GFDEBTN")


def test_cache_reuses_last_good_data_and_throttles_failures(monkeypatch):
    clock = [0]
    monkeypatch.setattr(debt, "monotonic", lambda: clock[0])
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) > 1:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "record_date": "2026-09-17",
                        "tot_pub_debt_out_amt": "40093343468150.50",
                    }
                ]
            },
        )

    async def check():
        cache = debt.DebtCache()
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            original, stale = await cache.get("daily", client)
            assert not stale
            assert await cache.get("daily", client) == (original, False)
            assert len(requests) == 1
            clock[0] = 3601
            assert await cache.get("daily", client) == (original, True)
            assert await cache.get("daily", client) == (original, True)
            assert len(requests) == 2
            assert await cache.get("GFDEBTN", client) == ([], True)

    asyncio.run(check())


@pytest.mark.parametrize("profile", DISPLAY_PROFILES)
@pytest.mark.parametrize("empty", [False, True])
def test_debt_rotation_and_native_images(monkeypatch, profile, empty):
    async def get_gerty(_):
        return SimpleNamespace(
            display_preferences=json.dumps(
                {
                    "national_debt": True,
                    "dashboard": True,
                    "_display": {"profile": profile},
                }
            ),
            utc_offset=0,
            refresh_time=300,
            json=lambda: "debt-test",
        )

    async def get_data():
        return {"nominal": [], "ratio": [], "stale": True} if empty else sample()

    monkeypatch.setattr(views_api, "get_gerty", get_gerty)
    monkeypatch.setattr(views_api, "get_national_debt_data", get_data)
    monkeypatch.setattr(views_api, "image_cache", ImageCache())
    app = FastAPI()
    app.include_router(views_api.gerty_api_router, prefix="/gerty")

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            response = await client.get("/gerty/api/v1/gerty/pages/test")
            assert response.status_code == 200
            manifest = response.json()
            assert manifest["screen_name"] == "national_debt"
            assert manifest["page_count"] == 2
            assert manifest["next_page"] == 1
            png = await client.get(manifest["image_url"])
            image = Image.open(BytesIO(png.content))
            expected = DISPLAY_PROFILES[profile]
            assert image.size == (expected["width"], expected["height"])
            assert image.mode == expected["mode"]
            if image.mode == "L":
                assert set(image.tobytes()) <= set(range(0, 256, 17))

    asyncio.run(check())
