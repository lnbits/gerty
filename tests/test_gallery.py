import asyncio
import json
from io import BytesIO
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from PIL import Image

from .. import gallery, views_api
from ..display_settings import DISPLAY_PROFILES
from ..image_cache import ImageCache
from .asgi import asgi_transport


def photo_bytes():
    output = BytesIO()
    Image.new("RGB", (100, 200), "red").save(output, "PNG")
    return output.getvalue()


@pytest.mark.parametrize("profile", DISPLAY_PROFILES.values())
def test_photo_fits_display(profile):
    image = Image.open(BytesIO(gallery.render_gallery(photo_bytes(), profile)))
    assert image.size == (profile["width"], profile["height"])
    assert image.mode == profile["mode"]
    assert image.getpixel((0, 0)) not in (0, (0, 0, 0))
    assert image.getpixel((image.width // 2, image.height // 2)) == image.getpixel(
        (0, 0)
    )
    if image.mode == "L":
        assert set(image.tobytes()) <= set(range(0, 256, 17))


@pytest.mark.parametrize("ids", [False, "photo", [1], [""], ["x"] * 101])
def test_reject_invalid_gallery(ids):
    with pytest.raises(HTTPException):
        gallery.gallery_ids({"_gallery": ids})


def test_validate_owner_and_empty_gallery(monkeypatch):
    calls = []

    async def get_asset(user, asset):
        calls.append((user, asset))
        raise HTTPException(422, "Not your photo")

    monkeypatch.setattr(gallery, "get_gallery_asset", get_asset)
    with pytest.raises(HTTPException):
        asyncio.run(gallery.validate_gallery({"gallery": True}, "owner"))
    with pytest.raises(HTTPException):
        asyncio.run(gallery.validate_gallery({"_gallery": ["private"]}, "owner"))
    assert calls == [("owner", "private")]


def test_gallery_rotation(monkeypatch):
    async def get_gerty(_):
        return SimpleNamespace(
            display_preferences=json.dumps({"gallery": True, "_gallery": ["a", "b"]}),
            wallet="wallet",
            utc_offset=0,
            refresh_time=60,
            json=lambda: "gallery-test",
        )

    async def get_wallet(wallet):
        assert wallet == "wallet"
        return SimpleNamespace(user="owner")

    seen = []

    async def get_asset(user, asset):
        assert user == "owner"
        seen.append(asset)
        return SimpleNamespace(data=photo_bytes())

    monkeypatch.setattr(views_api, "get_gerty", get_gerty)
    monkeypatch.setattr(views_api, "get_wallet", get_wallet)
    monkeypatch.setattr(views_api, "get_gallery_asset", get_asset)
    monkeypatch.setattr(views_api, "image_cache", ImageCache())
    monkeypatch.setattr(views_api, "gerty_should_sleep", lambda _: False)
    app = FastAPI()
    app.include_router(views_api.gerty_api_router)

    async def check():
        async with httpx.AsyncClient(
            transport=asgi_transport(app), base_url="http://test"
        ) as client:
            for page, next_page in [(0, 1), (1, 0)]:
                response = await client.get(f"/api/v1/gerty/pages/test/{page}")
                assert response.status_code == 200
                manifest = response.json()
                assert manifest["page_count"] == 2
                assert manifest["screen_name"] == "gallery"
                assert manifest["next_page"] == next_page
                image = await client.get(manifest["image_url"])
                Image.open(BytesIO(image.content)).verify()

    asyncio.run(check())
    assert seen == ["a", "b"]


@pytest.mark.parametrize("size", [(300, 100), (100, 300)])
def test_gallery_crops_from_center(size):
    source = Image.new("RGB", size, "blue")
    left, top = (size[0] - 100) // 2, (size[1] - 100) // 2
    source.paste("red", (left, top, left + 100, top + 100))
    buffer = BytesIO()
    source.save(buffer, "PNG")
    image = Image.open(
        BytesIO(
            gallery.render_gallery(
                buffer.getvalue(), {"width": 100, "height": 100, "mode": "RGB"}
            )
        )
    )
    assert image.getextrema() == ((255, 255), (0, 0), (0, 0))
