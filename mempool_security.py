"""Restrict custom mempool settings and pin requests to public IP addresses."""

import httpx
from fastapi import HTTPException
from lnbits.settings import settings
from lnbits.utils.safe_http import SafeHttpClient, validate_url

DEFAULT_MEMPOOL_ENDPOINT = "https://mempool.space"


def normalize_endpoint(raw):
    if raw is None:
        raw = DEFAULT_MEMPOOL_ENDPOINT
    if not isinstance(raw, str):
        raise HTTPException(422, "Invalid mempool URL.")
    try:
        url = httpx.URL(raw.strip())
    except httpx.InvalidURL as exc:
        raise HTTPException(422, "Invalid mempool URL.") from exc
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or "?" in raw
        or "#" in raw
    ):
        raise HTTPException(
            422, "Use an HTTP(S) mempool URL without credentials, query or fragment."
        )
    return str(url).rstrip("/")


async def resolve_endpoint(endpoint):
    try:
        return await validate_url(endpoint)
    except (ValueError, httpx.InvalidURL) as exc:
        raise HTTPException(422, "Mempool destination is not allowed.") from exc


async def validate_mempool_change(raw, user_id, current=None):
    endpoint = normalize_endpoint(raw)
    previous = normalize_endpoint(current)
    if endpoint != previous and user_id != settings.super_user:
        raise HTTPException(403, "Only super users can change the mempool URL.")
    await resolve_endpoint(endpoint)
    return endpoint


async def fetch_mempool_json(endpoint, path):
    try:
        async with SafeHttpClient() as client:
            response = await client.get(endpoint + path)
            response.raise_for_status()
            return response.json()
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(422, "Mempool request failed.") from exc
