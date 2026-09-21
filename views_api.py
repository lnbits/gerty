import asyncio
import json
import random
from datetime import datetime, timezone
from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from lnbits.core.crud import get_user, get_wallet
from lnbits.core.models import User, WalletTypeInfo
from lnbits.decorators import check_user_exists, require_admin_key, require_invoice_key
from starlette.datastructures import UploadFile

from .bitcoin_history import events_on, history_screen
from .block_explorer import get_block_explorer_data, render_block_explorer
from .colour_rendering import render_colour_screen
from .crud import (
    create_gerty,
    delete_gerty,
    get_gerty,
    get_gertys,
    get_mempool_info,
    update_gerty,
)
from .display_settings import DISPLAY_PROFILES, get_display_settings
from .gallery import (
    gallery_enabled,
    gallery_ids,
    gallery_limits,
    get_gallery_asset,
    render_gallery,
    validate_gallery,
    validate_gallery_image,
)
from .helpers import (
    get_satoshi,
    get_screen_data,
)
from .image_cache import image_cache
from .mempool_security import validate_mempool_change
from .models import CreateGerty, Gerty
from .rendering import render_screen
from .sleep_schedule import local_time, sleep_data, validate_schedule
from .wallet_history import get_wallet_history_data, render_wallet_history

gerty_api_router = APIRouter()


async def device_sleep_response(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return None


def validate_history_wallet(data):
    preferences = json.loads(data.display_preferences)
    try:
        validate_schedule(preferences)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if preferences.get("wallet_history") is True:
        keys = json.loads(data.lnbits_wallets or "[]")
        if not isinstance(keys, list) or any(
            not isinstance(key, str) or not key.strip() for key in keys
        ):
            raise HTTPException(422, "Wallet history requires a list of invoice keys.")


@gerty_api_router.get("/api/v1/gallery/settings")
async def api_gallery_settings(user: User = Depends(check_user_exists)):
    return await gallery_limits(user.id)


@gerty_api_router.post("/api/v1/gallery/photos")
async def api_gallery_upload(request: Request, user: User = Depends(check_user_exists)):
    from importlib import import_module

    limits = await gallery_limits(user.id)
    if not limits["enabled"]:
        raise HTTPException(403, "Gallery is disabled in LNbits asset settings.")
    # Parse only on upload so older LNbits installs can still load the extension.
    async with request.form() as form:
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise HTTPException(422, "Select a photo to upload.")
        # Check headers before LNbits generates a thumbnail or decodes the image.
        contents = await file.read(limits["max_bytes"] + 1)
        if len(contents) > limits["max_bytes"]:
            raise HTTPException(422, "Photo exceeds the LNbits asset size limit.")
        await asyncio.to_thread(validate_gallery_image, contents)
        await file.seek(0)
        try:
            service = import_module("lnbits.core.services.assets")
            asset = await service.create_user_asset(user.id, file, False)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    return {"id": asset.id}


@gerty_api_router.get("/api/v1/gerty", status_code=HTTPStatus.OK)
async def api_gertys(
    all_wallets: bool = Query(False),
    key_info: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Gerty]:
    wallet_ids = [key_info.wallet.id]
    if all_wallets:
        user = await get_user(key_info.wallet.user)
        wallet_ids = user.wallet_ids if user else []
    return await get_gertys(wallet_ids)


@gerty_api_router.post("/api/v1/gerty", status_code=HTTPStatus.CREATED)
async def api_link_create(
    data: CreateGerty,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> Gerty:
    if not data.wallet:
        data.wallet = key_info.wallet.id
    if data.wallet != key_info.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your wallet.")
    validate_history_wallet(data)
    data.mempool_endpoint = await validate_mempool_change(
        data.mempool_endpoint, key_info.wallet.user
    )
    await validate_gallery(json.loads(data.display_preferences), key_info.wallet.user)
    return await create_gerty(data)


@gerty_api_router.put("/api/v1/gerty/{gerty_id}", status_code=HTTPStatus.OK)
async def api_link_update(
    data: Gerty,
    gerty_id: str,
    key_info: WalletTypeInfo = Depends(require_admin_key),
) -> Gerty:

    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Gerty does not exist"
        )

    if gerty.wallet != key_info.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN,
            detail="Come on, seriously, this isn't your Gerty!",
        )

    validate_history_wallet(data)
    data.mempool_endpoint = await validate_mempool_change(
        data.mempool_endpoint, key_info.wallet.user, gerty.mempool_endpoint
    )
    await validate_gallery(json.loads(data.display_preferences), key_info.wallet.user)
    for key, value in data.dict().items():
        setattr(gerty, key, value)

    gerty.wallet = key_info.wallet.id
    gerty = await update_gerty(gerty)
    return gerty


@gerty_api_router.delete("/api/v1/gerty/{gerty_id}")
async def api_gerty_delete(
    gerty_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    gerty = await get_gerty(gerty_id)

    if not gerty:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Gerty does not exist."
        )

    if gerty.wallet != wallet.wallet.id:
        raise HTTPException(status_code=HTTPStatus.FORBIDDEN, detail="Not your Gerty.")

    await delete_gerty(gerty_id)
    raise HTTPException(status_code=HTTPStatus.NO_CONTENT)


@gerty_api_router.get("/api/v1/gerty/satoshiquote", status_code=HTTPStatus.OK)
async def api_gerty_satoshi(gerty_id: str = ""):
    if gerty_id and (sleep := await device_sleep_response(gerty_id)):
        return sleep
    return await get_satoshi()


@gerty_api_router.get("/api/v1/gerty/block-explorer", name="gerty_block_explorer")
async def api_gerty_block_explorer(
    gerty_id: str = "",
    key_info: WalletTypeInfo = Depends(require_invoice_key),
):
    """Render current Block explorer data; devices use their Gerty page URL."""
    if gerty_id and (sleep := await device_sleep_response(gerty_id)):
        return sleep
    try:
        data = await get_block_explorer_data()
    except Exception as exc:
        raise HTTPException(
            503, "Block explorer data temporarily unavailable."
        ) from exc
    png = await asyncio.to_thread(
        render_block_explorer, data, datetime.now(timezone.utc).strftime("%H:%M")
    )
    return Response(
        png,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@gerty_api_router.get("/api/v1/gerty/images/{revision}.png", name="gerty_image")
async def api_gerty_image(revision: str, preview: bool = False):
    snapshot = image_cache.get(revision)
    if snapshot is None:
        raise HTTPException(410, "Image expired; fetch the page manifest again.")
    gerty = await get_gerty(snapshot.key.split(":", 1)[0])
    if not preview and gerty and (sleep := sleep_data(gerty)):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return Response(
        snapshot.png,
        media_type="image/png",
        headers={
            "Cache-Control": "private, no-store",
            "ETag": f'"{revision}"',
        },
    )


@gerty_api_router.get("/api/v1/gerty/pages/{gerty_id}")
@gerty_api_router.get("/api/v1/gerty/pages/{gerty_id}/{p}")
async def api_gerty_json(
    request: Request, gerty_id: str, p: int = 0, preview: bool = False
):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if not preview and (sleep := sleep_data(gerty)):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    preferences = json.loads(gerty.display_preferences)
    try:
        device_type, colour_theme = get_display_settings(preferences)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    profile = DISPLAY_PROFILES[device_type]
    screens = [
        slug
        for slug, enabled in preferences.items()
        if slug != "_display" and enabled is True
    ]
    photo_ids = gallery_ids(preferences) if gallery_enabled() else []
    screens = [screen for screen in screens if screen != "gallery" or photo_ids]
    history_keys = (
        list(dict.fromkeys(json.loads(gerty.lnbits_wallets or "[]")))
        if "wallet_history" in screens
        else []
    )
    # Keep other screens in their configured position in the rotation.
    pages = [
        (screen, invoice_key)
        for screen in screens
        for invoice_key in (
            (history_keys or [None]) if screen == "wallet_history" else [None]
        )
    ]
    screens = [screen for screen, _ in pages]
    if not screens:
        raise HTTPException(422, "Enable at least one screen.")
    if p < 0 or p >= len(screens):
        # Saved hardware page numbers can become stale after disabling screens.
        # Continue the rotation at the first enabled page.
        p = 0
    updated = local_time(gerty, datetime.now(timezone.utc))
    history_events = events_on(updated.date()) if "bitcoin_history" in screens else []
    available = [
        i
        for i, screen in enumerate(screens)
        if screen != "bitcoin_history" or history_events
    ]
    if not available:
        raise HTTPException(
            422,
            "No screens available today. Enable another screen "
            "for days without a history event.",
        )
    p = next((i for i in available if i >= p), available[0])
    next_page = next((i for i in available if i > p), available[0])
    slug = screens[p]
    refresh = gerty.refresh_time if gerty.refresh_time is not None else 300
    if refresh <= 0:
        raise HTTPException(422, "Refresh time must be a positive number of seconds.")
    # Include configuration so edits invalidate snapshots immediately.
    key = f"{gerty_id}:{p}:{device_type}:{colour_theme}:{updated.date()}:{gerty.json()}"
    async with image_cache.lock:
        snapshot = image_cache.fresh(key)
    if snapshot is None:
        try:
            photo = None
            if slug == "gallery":
                wallet = await get_wallet(gerty.wallet) if gerty.wallet else None
                if not wallet:
                    raise HTTPException(404, "Gallery wallet no longer exists.")
                photo = await get_gallery_asset(wallet.user, random.choice(photo_ids))
            data = (
                {}
                if photo
                else (
                    history_screen(history_events, updated, refresh)
                    if slug == "bitcoin_history"
                    else (
                        await get_wallet_history_data(gerty, invoice_key=pages[p][1])
                        if slug == "wallet_history"
                        else (
                            await get_block_explorer_data()
                            if slug == "block_explorer"
                            else await get_screen_data(p, screens, gerty)
                        )
                    )
                )
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "Screen data temporarily unavailable.") from exc
        updated = local_time(gerty, datetime.now(timezone.utc))
        if photo:
            png = await asyncio.to_thread(render_gallery, photo.data, profile)
        elif slug == "wallet_history":
            png = await asyncio.to_thread(
                render_wallet_history,
                data,
                updated.strftime("%H:%M"),
                width=profile["width"],
                height=profile["height"],
                mode=profile["mode"],
            )
        elif profile["mode"] == "RGB":
            png = await asyncio.to_thread(
                render_colour_screen,
                data,
                slug,
                updated.strftime("%H:%M"),
                colour_theme,
                height=profile["height"],
                width=profile["width"],
            )
        elif slug == "block_explorer":
            png = await asyncio.to_thread(
                render_block_explorer, data, updated.strftime("%H:%M")
            )
        else:
            png = await asyncio.to_thread(
                render_screen, data, slug, updated.strftime("%H:%M")
            )
        async with image_cache.lock:
            # A concurrent request may already have populated this cache key.
            snapshot = image_cache.fresh(key)
            if snapshot is None:
                snapshot = image_cache.put(key, png, refresh)
    return Response(
        content=json.dumps(
            {
                "schema_version": 1,
                "sleep_mode": False,
                "image_url": str(
                    request.url_for(
                        "gerty_image", revision=snapshot.revision
                    ).include_query_params(preview="true")
                    if preview
                    else request.url_for("gerty_image", revision=snapshot.revision)
                ),
                "image_revision": snapshot.revision,
                "refresh_seconds": refresh,
                "page": p,
                "page_count": len(screens),
                "next_page": next_page,
                "screen_name": slug,
                "device_type": device_type,
                "width": profile["width"],
                "height": profile["height"],
                "colour_theme": (colour_theme if profile["mode"] == "RGB" else None),
            }
        ),
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


###########CACHED MEMPOOL##############


@gerty_api_router.get("/api/v1/gerty/fees-recommended/{gerty_id}")
async def api_gerty_get_fees_recommended(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("fees_recommended", gerty)


@gerty_api_router.get("/api/v1/gerty/hashrate-1w/{gerty_id}")
async def api_gerty_get_hashrate_1w(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("hashrate_1w", gerty)


@gerty_api_router.get("/api/v1/gerty/hashrate-1m/{gerty_id}")
async def api_gerty_get_hashrate_1m(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("hashrate_1m", gerty)


@gerty_api_router.get("/api/v1/gerty/statistics/{gerty_id}")
async def api_gerty_get_statistics(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("statistics", gerty)


@gerty_api_router.get("/api/v1/gerty/difficulty-adjustment/{gerty_id}")
async def api_gerty_get_difficulty_adjustment(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("difficulty_adjustment", gerty)


@gerty_api_router.get("/api/v1/gerty/tip-height/{gerty_id}")
async def api_gerty_get_tip_height(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("tip_height", gerty)


@gerty_api_router.get("/api/v1/gerty/mempool/{gerty_id}")
async def api_gerty_get_mempool(gerty_id):
    gerty = await get_gerty(gerty_id)
    if not gerty:
        raise HTTPException(404, "Gerty does not exist.")
    if sleep := sleep_data(gerty):
        return JSONResponse(sleep, headers={"Cache-Control": "no-store"})
    return await get_mempool_info("mempool", gerty)
