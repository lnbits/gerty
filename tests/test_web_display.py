"""Web colours must affect snapshots without changing hardware rendering."""

import asyncio
import json
from datetime import date
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image, ImageColor

from .. import views_api
from ..display_settings import COLOUR_THEMES
from ..image_cache import ImageCache
from .asgi import asgi_transport
from .test_national_debt import sample


@pytest.mark.parametrize("profile", ["web_page", "colour_480x272"])
@pytest.mark.parametrize(
    "screen",
    ["onchain_block_height", "national_debt", "wallet_history", "block_explorer"],
)
def test_web_palette_and_hardware_independence(monkeypatch, profile, screen):
    preferences = {screen: True, "_display": {"profile": profile}}

    async def gerty(_):
        return SimpleNamespace(
            display_preferences=json.dumps(preferences),
            utc_offset=0,
            lnbits_wallets="[]",
            refresh_time=5,
            model_dump_json=lambda: json.dumps(preferences),
        )

    async def data(*args, **kwargs):
        if screen == "block_explorer":
            return {
                "blocks": [{"height": 100, "timestamp": 1700000000}],
                "estimates": {"1": 12, "3": 8, "6": 5, "144": 2},
                "intervals": [(100, 12), (99, 5)],
                "histogram": [(0.5, 1000000), (200, 1)],
            }
        if screen == "national_debt":
            return sample()
        if screen == "wallet_history":
            return {
                "wallet_count": 1,
                "wallet_name": "Test wallet",
                "points": [(date(2026, 1, n), n * 100) for n in range(1, 6)],
            }
        return {"areas": [[{"value": "Height"}, {"value": "100"}]]}

    monkeypatch.setattr(views_api, "get_gerty", gerty)
    monkeypatch.setattr(views_api, "get_screen_data", data)
    monkeypatch.setattr(views_api, "get_block_explorer_data", data)
    monkeypatch.setattr(views_api, "get_national_debt_data", data)
    monkeypatch.setattr(views_api, "get_wallet_history_data", data)
    monkeypatch.setattr(views_api, "image_cache", ImageCache())
    app = FastAPI()
    app.include_router(views_api.gerty_api_router, prefix="/gerty")

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            params = {"web_primary": "#123456", "web_secondary": "#abcdef"}
            path = "/gerty/api/v1/gerty/pages/test"
            response = await client.get(path, params=params)
            assert response.status_code == 200
            manifest = response.json()
            assert manifest["device_type"] == profile
            image = Image.open(
                BytesIO((await client.get(manifest["image_url"])).content)
            )
            expected_size = (1920, 1088) if profile == "web_page" else (480, 272)
            assert image.size == expected_size and image.mode == "RGB"
            assert (manifest["width"], manifest["height"]) == expected_size
            if profile == "web_page":
                pixels = {
                    colour for _, colour in image.getcolors(image.width * image.height)
                }
                assert ImageColor.getrgb(params["web_primary"]) in pixels
                assert ImageColor.getrgb(params["web_secondary"]) in pixels
                assert image.getpixel((0, 0)) == ImageColor.getrgb(
                    COLOUR_THEMES["Midnight"]["background"]
                )
            params["web_primary"] = "#654321"
            params["web_dark"] = "false"
            changed = (await client.get(path, params=params)).json()
            assert (changed["image_revision"] != manifest["image_revision"]) == (
                profile == "web_page"
            )
            if profile == "web_page":
                image = Image.open(
                    BytesIO((await client.get(changed["image_url"])).content)
                )
                assert image.getpixel((0, 0)) == ImageColor.getrgb(
                    COLOUR_THEMES["Paper"]["background"]
                )
            params["web_primary"] = "invalid"
            assert (await client.get(path, params=params)).status_code == 422

    asyncio.run(check())
