import asyncio
from datetime import datetime, timedelta, timezone
from io import BytesIO
from types import SimpleNamespace

import pytest
from PIL import Image

from .. import wallet_history


def test_daily_balances_fees_gaps_and_duplicate_wallets(monkeypatch):
    now = datetime(2026, 9, 16, 12, tzinfo=timezone.utc)
    wallets = {
        "a": SimpleNamespace(id="one", balance_msat=8000),
        "duplicate": SimpleNamespace(id="one", balance_msat=8000),
        "b": SimpleNamespace(id="two", balance_msat=3000),
    }
    calls = []

    async def get_wallet(*, key):
        return wallets[key]

    async def get_history(*, wallet_id, group, filters):
        calls.append(wallet_id)
        assert group == "day"
        assert filters.filters[0].field == "time"
        return (
            []
            if wallet_id == "two"
            else [
                SimpleNamespace(
                    date=now - timedelta(days=3),
                    balance=10000,
                    income=10000,
                    spending=0,
                ),
                SimpleNamespace(
                    date=now - timedelta(days=1), balance=8000, income=0, spending=2000
                ),
            ]
        )

    monkeypatch.setattr(wallet_history, "get_wallet_for_key", get_wallet)
    monkeypatch.setattr(wallet_history, "get_payments_history", get_history)
    result = asyncio.run(
        wallet_history.get_wallet_history_data(
            SimpleNamespace(lnbits_wallets='["a", "duplicate", "b"]'), now
        )
    )
    assert result["wallet_count"] == 2
    assert calls == ["one", "two"]
    assert len(result["points"]) == 30
    assert [value for _, value in result["points"]][-5:] == [3, 13, 13, 11, 11]
    assert result["points"][-1][0] == now.date()


def test_empty_and_invalid_wallets(monkeypatch):
    result = asyncio.run(
        wallet_history.get_wallet_history_data(SimpleNamespace(lnbits_wallets=""))
    )
    assert result["wallet_count"] == 0

    async def missing(*, key):
        return None

    monkeypatch.setattr(wallet_history, "get_wallet_for_key", missing)
    with pytest.raises(ValueError, match="unavailable"):
        asyncio.run(
            wallet_history.get_wallet_history_data(
                SimpleNamespace(lnbits_wallets='["invalid"]')
            )
        )


@pytest.mark.parametrize(
    "width,height,mode",
    [(240, 240, "RGB"), (480, 272, "RGB"), (480, 320, "RGB"), (960, 540, "L")],
)
@pytest.mark.parametrize(
    "values",
    [[0] * 30, [1000] * 30, list(range(30)), list(range(-15, 15)), [0.001] * 30],
)
def test_display_contract(width, height, mode, values):
    today = datetime(2026, 9, 16).date()
    data = {
        "wallet_count": 1,
        "points": [
            (today - timedelta(days=29 - i), value) for i, value in enumerate(values)
        ],
    }
    image = Image.open(
        BytesIO(
            wallet_history.render_wallet_history(
                data, "12:00", width=width, height=height, mode=mode
            )
        )
    )
    assert image.size == (width, height)
    assert image.mode == mode
    if mode == "L":
        assert set(image.tobytes()) <= set(range(0, 256, 17))
    elif any(values):
        colours = image.getcolors(width * height)
        assert colours is not None and len(colours) > 30


@pytest.mark.parametrize(
    "profile", ["colour_240x240", "colour_480x272", "colour_480x320", "epaper_960x540"]
)
def test_history_manifest_and_data_failure(monkeypatch, profile):
    import json

    import httpx
    from fastapi import FastAPI

    from .. import views_api
    from ..display_settings import DISPLAY_PROFILES
    from ..image_cache import ImageCache
    from .asgi import asgi_transport

    async def get_gerty(_):
        return SimpleNamespace(
            display_preferences=json.dumps(
                {
                    "wallet_history": True,
                    "dashboard": True,
                    "_display": {"profile": profile},
                }
            ),
            utc_offset=0,
            refresh_time=300,
            json=lambda: "history-test",
        )

    async def get_data(_):
        return {"wallet_count": 1, "points": [(datetime(2026, 9, 16).date(), 1000)]}

    monkeypatch.setattr(views_api, "get_gerty", get_gerty)
    monkeypatch.setattr(views_api, "get_wallet_history_data", get_data)
    monkeypatch.setattr(views_api, "gerty_should_sleep", lambda _: False)
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
            assert manifest["screen_name"] == "wallet_history"
            assert manifest["next_page"] == 1
            png = await client.get(manifest["image_url"])
            image = Image.open(BytesIO(png.content))
            expected = DISPLAY_PROFILES[profile]
            assert image.size == (expected["width"], expected["height"])
            assert image.mode == expected["mode"]

            async def fail(_):
                raise RuntimeError("private wallet data")

            monkeypatch.setattr(views_api, "get_wallet_history_data", fail)
            monkeypatch.setattr(views_api, "image_cache", ImageCache())
            failed = await client.get("/gerty/api/v1/gerty/pages/test")
            assert failed.status_code == 503
            assert "private wallet" not in failed.text

    asyncio.run(check())


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("keys", [[], ["one"], ["one", "two"]])
def test_history_accepts_only_one_invoice_key(enabled, keys):
    import json

    from fastapi import HTTPException

    from ..views_api import validate_history_wallet

    data = SimpleNamespace(
        display_preferences=json.dumps({"wallet_history": enabled}),
        lnbits_wallets=json.dumps(keys),
    )
    if enabled and len(keys) > 1:
        with pytest.raises(HTTPException) as error:
            validate_history_wallet(data)
        assert error.value.status_code == 422
    else:
        validate_history_wallet(data)
