"""Renderer/cache tests require no LNbits database or external data services."""

import importlib.util
import sys
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from .asgi import asgi_transport


def load_module(name):
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).parents[1] / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


rendering = load_module("rendering")
cache_module = load_module("image_cache")


def test_png_contract():
    data = {
        "title": "Mining Data",
        "areas": [
            [
                {"value": "Current hashrate", "size": 12},
                {"value": "123.45 Ehash", "size": 40},
            ]
        ]
        * 4,
    }
    png = rendering.render_screen(data, "dashboard_mining", "12:34")
    image = Image.open(BytesIO(png))
    assert image.size == (960, 540)
    assert image.mode == "L"
    assert not image.info.get("interlace")
    assert len(png) < 2 * 1024 * 1024
    assert set(image.tobytes()) <= set(range(0, 256, 17))
    assert image.getextrema() == (0, 255)


def test_empty_and_long_content():
    for areas in ([], [[{"value": "longword" * 200, "size": 80}]]):
        png = rendering.render_screen({"title": "", "areas": areas}, "quote", "12:34")
        Image.open(BytesIO(png)).verify()


def test_cache_revisions_limits_and_expiry():
    cache = cache_module.ImageCache(max_bytes=6)
    first = cache.put("a", b"123", 30)
    assert cache.fresh("a") is first
    assert cache.get(first.revision).png == b"123"
    assert cache.put("a", b"123", 30).revision == first.revision
    assert cache.size == 3
    second = cache.put("a", b"456", 30)
    assert second.revision != first.revision
    cache.put("b", b"789", 30)
    assert cache.get(first.revision) is None
    assert cache.size == 6
    cache.max_age = 0
    assert cache.get(second.revision) is None
    assert cache.size == 0


def test_stale_snapshot_still_downloadable():
    cache = cache_module.ImageCache()
    snapshot = cache.put("a", b"png", 0)
    assert cache.fresh("a") is None
    assert cache.get(snapshot.revision) is snapshot


@pytest.mark.parametrize("refresh", [5, 900])
def test_manifest_and_image_routes(monkeypatch, refresh):
    import asyncio
    from types import SimpleNamespace

    import httpx
    from fastapi import FastAPI

    from .. import views_api

    async def get_gerty(_):
        return SimpleNamespace(
            display_preferences='{"dashboard": true, "quote": true}',
            utc_offset=0,
            refresh_time=refresh,
            json=lambda: '{"id":"test"}',
        )

    async def get_data(*_):
        return {"title": "Device name", "areas": []}

    monkeypatch.setattr(views_api, "get_gerty", get_gerty)
    monkeypatch.setattr(views_api, "gerty_should_sleep", lambda _: False)
    monkeypatch.setattr(views_api, "get_screen_data", get_data)
    monkeypatch.setattr(views_api, "image_cache", cache_module.ImageCache())
    app = FastAPI()
    app.include_router(views_api.gerty_api_router, prefix="/gerty")

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            response = await client.get("/gerty/api/v1/gerty/pages/test")
            assert response.status_code == 200
            manifest = response.json()
            assert manifest["page"] == 0
            assert manifest["refresh_seconds"] == refresh
            assert manifest["next_page"] == 1
            assert manifest["screen_name"] == "dashboard"
            repeated = await client.get("/gerty/api/v1/gerty/pages/test/0")
            assert repeated.json()["image_revision"] == manifest["image_revision"]
            image = await client.get(manifest["image_url"])
            assert image.headers["content-type"] == "image/png"
            Image.open(BytesIO(image.content)).verify()
            for requested in (-1, 2, 99):
                fallback = await client.get(
                    f"/gerty/api/v1/gerty/pages/test/{requested}"
                )
                assert fallback.status_code == 200
                assert fallback.json()["page"] == 0
                assert fallback.json()["next_page"] == 1
                assert fallback.json()["screen_name"] == "dashboard"
                assert fallback.json()["image_revision"] == manifest["image_revision"]
            last = await client.get("/gerty/api/v1/gerty/pages/test/1")
            assert last.json()["next_page"] == 0
            views_api.image_cache.max_age = 0
            assert (await client.get(manifest["image_url"])).status_code == 410

    asyncio.run(check())


def test_block_explorer_live_endpoint(monkeypatch):
    import asyncio

    import httpx
    from fastapi import FastAPI

    from .. import views_api

    async def fetch():
        return {
            "height": 100,
            "blocks": [],
            "estimates": {},
            "histogram": [],
            "intervals": [],
        }

    monkeypatch.setattr(views_api, "get_block_explorer_data", fetch)

    app = FastAPI()
    app.dependency_overrides[views_api.require_invoice_key] = lambda: None
    app.include_router(views_api.gerty_api_router, prefix="/gerty")

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            response = await client.get("/gerty/api/v1/gerty/block-explorer")
            assert response.status_code == 200
            assert response.headers["content-type"] == "image/png"
            image = Image.open(BytesIO(response.content))
            assert image.size == (960, 540)

    asyncio.run(check())
