"""Restrict custom mempool settings and pin requests to public IP addresses."""

import asyncio
import ipaddress
import socket

import httpx
from fastapi import HTTPException
from lnbits.settings import settings

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


def public_ip(address):
    try:
        ip = ipaddress.ip_address(address)
    except ValueError as exc:
        raise HTTPException(422, "Invalid mempool IP address.") from exc
    if (
        not ip.is_global
        or ip.is_multicast
        or ip.is_reserved
        or "%" in address
    ):
        raise HTTPException(422, "Mempool URLs must resolve only to public IP addresses.")
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped:
            public_ip(str(ip.ipv4_mapped))
        if ip.sixtofour or ip.teredo:
            raise HTTPException(422, "IPv6 transition addresses are not supported.")
    return str(ip)


async def resolve_endpoint(endpoint):
    url = httpx.URL(endpoint)
    try:
        ipaddress.ip_address(url.host)
    except ValueError:
        try:
            records = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(
                    url.host, url.port or (443 if url.scheme == "https" else 80),
                    type=socket.SOCK_STREAM,
                ),
                timeout=5,
            )
        except (OSError, asyncio.TimeoutError) as exc:
            raise HTTPException(422, "Could not resolve the mempool hostname.") from exc
        addresses = [public_ip(record[4][0]) for record in records]
        if not addresses:
            raise HTTPException(422, "Could not resolve the mempool hostname.")
        # Prefer IPv4 on hosts without IPv6 routing; every answer is checked above.
        return sorted(set(addresses), key=lambda address: ipaddress.ip_address(address).version)[0]
    return public_ip(url.host)


async def validate_mempool_change(raw, user_id, current=None):
    endpoint = normalize_endpoint(raw)
    previous = normalize_endpoint(current)
    if endpoint != previous and user_id != settings.super_user:
        raise HTTPException(403, "Only super users can change the mempool URL.")
    await resolve_endpoint(endpoint)
    return endpoint


async def fetch_mempool_json(endpoint, path, address):
    url = httpx.URL(endpoint + path)
    # Connect to the validated IP, preserving Host and TLS certificate validation.
    # Never resolve the hostname again or route through an environment proxy.
    async with httpx.AsyncClient(follow_redirects=False, trust_env=False) as client:
        response = await client.get(
            url.copy_with(host=address),
            headers={"Host": url.netloc.decode("ascii")},
            extensions={"sni_hostname": url.host},
        )
        response.raise_for_status()
        return response.json()
