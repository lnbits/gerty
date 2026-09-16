"""Gallery photos use LNbits account assets, never arbitrary URLs or paths."""

from importlib import import_module
from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps


def gallery_ids(preferences):
    ids = preferences.get("_gallery", [])
    if (
        not isinstance(ids, list)
        or len(ids) > 100
        or any(not isinstance(item, str) or not item or len(item) > 64 for item in ids)
    ):
        raise HTTPException(422, "Gallery must contain at most 100 photo IDs.")
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
        canvas = canvas.convert("L").point([round(i / 17) * 17 for i in range(256)])
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()
