from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from .. import crud
from ..models import CreateGerty, Gerty


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_stored_private_endpoint_is_rejected_before_cache(monkeypatch, cached):
    entry = SimpleNamespace(data="{}") if cached else None
    db = SimpleNamespace(fetchone=AsyncMock(return_value=entry))
    monkeypatch.setattr(crud, "db", db)
    fetch = AsyncMock()
    monkeypatch.setattr(crud, "fetch_mempool_json", fetch)
    gerty = SimpleNamespace(
        mempool_endpoint="http://127.0.0.1",
        time=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )

    with pytest.raises(HTTPException) as exc:
        await crud.get_mempool_info("fees_recommended", gerty)

    assert exc.value.status_code == 422
    db.fetchone.assert_not_awaited()
    fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_writes_preserve_custom_endpoint(monkeypatch):
    db = SimpleNamespace(insert=AsyncMock(), update=AsyncMock())
    monkeypatch.setattr(crud, "db", db)
    data = {
        "name": "Test",
        "type": "Gerty",
        "utc_offset": 0,
        "refresh_time": 300,
        "wallet": "wallet",
        "lnbits_wallets": "[]",
        "exchange": "USD",
        "urls": "[]",
        "display_preferences": "{}",
        "mempool_endpoint": "https://mempool.example.com",
    }
    created = await crud.create_gerty(CreateGerty.parse_obj(data))
    assert created.mempool_endpoint == data["mempool_endpoint"]
    db.insert.assert_awaited_once_with("gerty.gertys", created)
    updated = await crud.update_gerty(Gerty.parse_obj({"id": "existing", **data}))
    assert updated.mempool_endpoint == data["mempool_endpoint"]
    db.update.assert_awaited_once_with("gerty.gertys", updated)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_public_self_destination_rejected_before_cache(monkeypatch):
    import asyncio
    import socket

    from lnbits.settings import settings

    monkeypatch.setattr(settings, "lnbits_outbound_host_ips", ["8.8.8.8"])
    monkeypatch.setattr(settings, "lnbits_callback_url_rules", [])
    monkeypatch.setattr(
        asyncio.get_running_loop(),
        "getaddrinfo",
        AsyncMock(
            return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
        ),
    )
    db = SimpleNamespace(fetchone=AsyncMock())
    monkeypatch.setattr(crud, "db", db)
    with pytest.raises(HTTPException):
        await crud.get_mempool_info(
            "fees_recommended",
            SimpleNamespace(mempool_endpoint="https://alias.example"),
        )
    db.fetchone.assert_not_awaited()


@pytest.mark.anyio
async def test_fetch_revalidates_after_cache_check(monkeypatch):
    import asyncio
    import socket

    from lnbits.settings import settings

    from .. import mempool_security

    monkeypatch.setattr(settings, "lnbits_callback_url_rules", [])
    resolver = AsyncMock(
        side_effect=[
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))],
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))],
        ]
    )
    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", resolver)
    await mempool_security.resolve_endpoint("https://mempool.example")
    with pytest.raises(HTTPException):
        await mempool_security.fetch_mempool_json(
            "https://mempool.example", "/api/blocks"
        )
    assert resolver.await_count == 2


@pytest.mark.anyio
async def test_endpoint_changes_remain_superuser_only(monkeypatch):
    from lnbits.settings import settings

    from .. import mempool_security

    monkeypatch.setattr(settings, "super_user", "superuser")
    resolver = AsyncMock()
    monkeypatch.setattr(mempool_security, "resolve_endpoint", resolver)
    with pytest.raises(HTTPException) as exc:
        await mempool_security.validate_mempool_change("https://custom.example", "user")
    assert exc.value.status_code == 403
    resolver.assert_not_awaited()
    assert (
        await mempool_security.validate_mempool_change(
            "https://custom.example", "superuser"
        )
        == "https://custom.example"
    )
