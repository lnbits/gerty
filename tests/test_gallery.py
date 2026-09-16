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


@pytest.mark.parametrize("ids", [False, "photo", [1], [""]])
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

    monkeypatch.setattr(views_api, "gallery_enabled", lambda: True)
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


@pytest.mark.parametrize(
    "maximum,user,expected",
    [(3, "user", 3), (3, "root", None), (3, "exempt", None), (0, "root", None)],
)
def test_account_asset_limits(monkeypatch, maximum, user, expected):
    monkeypatch.setattr(
        gallery,
        "settings",
        SimpleNamespace(
            lnbits_max_assets_per_user=maximum,
            lnbits_max_asset_size_mb=0.5,
            is_super_user=lambda user_id: user_id == "root",
            is_unlimited_assets_user=lambda user_id: user_id in {"root", "exempt"},
        ),
    )

    async def count(user_id):
        assert user_id == user
        return 3

    monkeypatch.setattr(
        gallery, "import_module", lambda _: SimpleNamespace(get_user_assets_count=count)
    )
    limits = asyncio.run(gallery.gallery_limits(user))
    assert limits["enabled"] == (maximum > 0)
    assert limits["max_assets"] == expected
    assert limits["instance_max_assets"] == maximum
    assert limits["asset_count"] == (3 if maximum else 0)
    assert limits["upload_max_bytes"] == 524288
    assert limits["max_bytes"] == 524288


def test_no_fixed_gallery_count_cap():
    ids = [str(index) for index in range(150)]
    assert gallery.gallery_ids({"_gallery": ids}) == ids


def test_gallery_disabled_rejects_enable(monkeypatch):
    monkeypatch.setattr(gallery, "gallery_enabled", lambda: False)
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            gallery.validate_gallery({"gallery": True, "_gallery": ["photo"]}, "root")
        )
    assert error.value.status_code == 403


def test_upload_uses_lnbits_storage_and_limits(monkeypatch):
    import importlib
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request
    from lnbits.core.models import User
    from starlette.datastructures import UploadFile

    upload = UploadFile(filename="photo.png", file=BytesIO(photo_bytes()))
    user = MagicMock(spec=User)
    user.id = "root"
    request = MagicMock(spec=Request)
    request.form.return_value.__aenter__ = AsyncMock(return_value={"file": upload})
    request.form.return_value.__aexit__ = AsyncMock(return_value=False)
    limits = AsyncMock(return_value={"enabled": False})
    monkeypatch.setattr(views_api, "gallery_limits", limits)
    with pytest.raises(HTTPException) as error:
        asyncio.run(views_api.api_gallery_upload(request, user))
    assert error.value.status_code == 403

    limits.return_value = {"enabled": True, "max_bytes": 1500000}
    create = AsyncMock(return_value=SimpleNamespace(id="stored"))
    real_import = importlib.import_module
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name, *args: (
            SimpleNamespace(create_user_asset=create)
            if name == "lnbits.core.services.assets"
            else real_import(name, *args)
        ),
    )
    assert asyncio.run(views_api.api_gallery_upload(request, user)) == {"id": "stored"}
    create.assert_awaited_once_with("root", upload, False)
    create.side_effect = ValueError("File limit exceeded")
    with pytest.raises(HTTPException) as error:
        asyncio.run(views_api.api_gallery_upload(request, user))
    assert error.value.status_code == 422
    assert error.value.detail == "File limit exceeded"


def png_header(width, height):
    import struct
    import zlib

    data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    crc = zlib.crc32(b"IHDR" + data)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", len(data))
        + b"IHDR"
        + data
        + struct.pack(">I", crc)
        + b"\x00\x00\x00\x00IDAT"
    )


@pytest.mark.parametrize("size", [(2001, 1000), (1000, 2001), (20000, 20000)])
def test_oversized_gallery_rejected_before_decode(monkeypatch, size):
    def must_not_decode(*_args, **_kwargs):
        pytest.fail("Oversized photo was decoded")

    monkeypatch.setattr(Image.Image, "load", must_not_decode)
    monkeypatch.setattr(gallery.ImageOps, "exif_transpose", must_not_decode)
    with pytest.raises(HTTPException) as error:
        gallery.render_gallery(png_header(*size), DISPLAY_PROFILES["epaper_960x540"])
    assert error.value.status_code == 422


def test_pixel_limit_is_inclusive():
    gallery.validate_gallery_image(png_header(2000, 1000))


def test_oversized_upload_rejected_before_lnbits_thumbnail(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request
    from lnbits.core.models import User
    from starlette.datastructures import UploadFile

    request = MagicMock(spec=Request)
    user = MagicMock(spec=User)
    user.id = "user"
    upload = UploadFile(filename="large.png", file=BytesIO(png_header(2001, 1000)))
    request.form.return_value.__aenter__ = AsyncMock(return_value={"file": upload})
    request.form.return_value.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(
        views_api,
        "gallery_limits",
        AsyncMock(return_value={"enabled": True, "max_bytes": 1500000}),
    )
    # The local test LNbits has no asset service; reaching it would fail this test.
    with pytest.raises(HTTPException) as error:
        asyncio.run(views_api.api_gallery_upload(request, user))
    assert error.value.status_code == 422
    assert "2 million pixels" in error.value.detail
