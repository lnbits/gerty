import asyncio
import json
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from PIL import Image

from .. import views_api
from ..colour_rendering import render_colour_screen
from ..display_settings import COLOUR_THEMES, get_display_settings
from ..image_cache import ImageCache
from .asgi import asgi_transport


@pytest.mark.parametrize("theme", list(COLOUR_THEMES))
@pytest.mark.parametrize("width,height", [(480, 320), (480, 272), (240, 240)])
@pytest.mark.parametrize(
    "slug",
    [
        "fun_satoshi_quotes",
        "dashboard_onchain",
        "onchain_block_height",
        "url_checker",
        "lnbits_wallets_balance",
        "block_explorer",
    ],
)
def test_native_colour_images(theme, slug, width, height):
    if slug == "block_explorer":
        data = {
            "height": 100,
            "blocks": [],
            "estimates": {},
            "intervals": [(100, 12), (99, 5)],
            "histogram": [(0.5, 1000000), (200, 1)],
        }
    else:
        data = {
            "title": "Onchain Data",
            "areas": [
                [
                    {"value": "Current block height", "size": 20},
                    {"value": "966,345", "size": 80},
                ]
            ],
        }
        if slug == "dashboard_onchain":
            data["areas"] *= 4
    png = render_colour_screen(data, slug, "12:34", theme, height=height, width=width)
    image = Image.open(BytesIO(png))
    assert image.size == (width, height)
    assert image.mode == "RGB"
    assert len(png) < 2 * 1024 * 1024
    assert len({image.getpixel((x, 0)) for x in range(width)}) == 1
    pixel = image.getpixel((0, 0))
    assert isinstance(pixel, tuple) and len(pixel) == 3
    r, g, b = pixel
    assert r != g or g != b


def test_profile_defaults_and_invalid_theme():
    assert get_display_settings({}) == ("epaper_960x540", "Orange Pill")
    with pytest.raises(ValueError):
        get_display_settings({"_display": {"theme": "unknown"}})


@pytest.mark.parametrize("width,height", [(480, 320), (480, 272), (240, 240)])
def test_api_image_matches_device_and_theme(monkeypatch, width, height):
    preferences = {
        "onchain_block_height": True,
        "_display": {"profile": f"colour_{width}x{height}", "theme": "Cypherpunk"},
    }

    async def gerty(_):
        return SimpleNamespace(
            display_preferences=json.dumps(preferences),
            utc_offset=0,
            refresh_time=5,
            json=lambda: json.dumps(preferences),
        )

    async def data(*_):
        return {
            "title": "",
            "areas": [[{"value": "Height", "size": 20}, {"value": "100", "size": 80}]],
        }

    monkeypatch.setattr(views_api, "get_gerty", gerty)
    monkeypatch.setattr(views_api, "get_screen_data", data)
    monkeypatch.setattr(views_api, "image_cache", ImageCache())
    app = FastAPI()
    app.include_router(views_api.gerty_api_router, prefix="/gerty")

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            manifest = (await client.get("/gerty/api/v1/gerty/pages/test")).json()
            assert manifest["device_type"] == f"colour_{width}x{height}"
            assert (manifest["width"], manifest["height"]) == (width, height)
            assert manifest["page_count"] == 1
            png = (await client.get(manifest["image_url"])).content
            assert Image.open(BytesIO(png)).mode == "RGB"
            assert Image.open(BytesIO(png)).size == (width, height)
            preferences["_display"]["theme"] = "Bright day"
            changed = (await client.get("/gerty/api/v1/gerty/pages/test")).json()
            assert changed["image_revision"] != manifest["image_revision"]
            preferences["_display"]["profile"] = "epaper_960x540"
            mono = (await client.get("/gerty/api/v1/gerty/pages/test")).json()
            assert mono["device_type"] == "epaper_960x540"
            png = (await client.get(mono["image_url"])).content
            image = Image.open(BytesIO(png))
            assert image.size == (960, 540) and image.mode == "L"

    asyncio.run(check())
