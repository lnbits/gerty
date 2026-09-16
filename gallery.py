"""Gallery photos use LNbits account assets, never arbitrary URLs or paths."""

from importlib import import_module
from io import BytesIO

from fastapi import HTTPException
from lnbits.settings import settings
from PIL import Image, ImageEnhance, ImageOps


def gallery_enabled():
    return getattr(settings, "lnbits_max_assets_per_user", 0) > 0


async def gallery_limits(user_id):
    max_assets = getattr(settings, "lnbits_max_assets_per_user", 0)
    max_bytes = int(getattr(settings, "lnbits_max_asset_size_mb", 0) * 1024 * 1024)
    unlimited = getattr(settings, "is_super_user", lambda _: False)(user_id) or getattr(
        settings, "is_unlimited_assets_user", lambda _: False
    )(user_id)
    count = 0
    if gallery_enabled():
        try:
            assets = import_module("lnbits.core.crud.assets")
        except ImportError as exc:
            raise HTTPException(
                503, "Gallery requires LNbits asset storage support."
            ) from exc
        count = await assets.get_user_assets_count(user_id)
    return {
        "enabled": gallery_enabled(),
        "max_assets": None if unlimited else max_assets,
        "instance_max_assets": max_assets,
        "asset_count": count,
        "max_bytes": max_bytes,
        "upload_max_bytes": min(1500000, max_bytes),
    }


def gallery_ids(preferences):
    ids = preferences.get("_gallery", [])
    if not isinstance(ids, list) or any(
        not isinstance(item, str) or not item or len(item) > 64 for item in ids
    ):
        raise HTTPException(422, "Gallery must contain valid photo IDs.")
    return list(dict.fromkeys(ids))


async def get_gallery_asset(user_id, asset_id):
    try:
        get_user_asset = import_module("lnbits.core.crud.assets").get_user_asset
    except ImportError as exc:
        raise HTTPException(
            503, "Gallery requires LNbits asset storage support."
        ) from exc
    asset = await get_user_asset(user_id, asset_id)
    if not asset or asset.mime_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(422, "Gallery photo is missing or is not a JPEG or PNG.")
    return asset


async def validate_gallery(preferences, user_id):
    ids = gallery_ids(preferences)
    if preferences.get("gallery") is True and not gallery_enabled():
        raise HTTPException(403, "Gallery is disabled in LNbits asset settings.")
    if preferences.get("gallery") is True and not ids:
        raise HTTPException(422, "Upload at least one Gallery photo.")
    for asset_id in ids:
        await get_gallery_asset(user_id, asset_id)


def render_gallery(contents, profile):
    with Image.open(BytesIO(contents)) as source:
        photo = ImageOps.exif_transpose(source).convert("RGBA")
        photo = ImageOps.fit(
            photo,
            (profile["width"], profile["height"]),
            method=Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        canvas = Image.new("RGB", photo.size, "black")
        canvas.paste(photo, (0, 0), photo)
    if profile["mode"] == "L":
        canvas = ImageEnhance.Brightness(canvas.convert("L")).enhance(1.2)
        canvas = canvas.point([round(i / 17) * 17 for i in range(256)])
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()
