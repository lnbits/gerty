from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from .. import crud
from ..models import CreateGerty, Gerty


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True])
async def test_stored_custom_endpoint_cannot_control_fetch_or_cache(
    monkeypatch, cached
):
    entry = SimpleNamespace(data="{}") if cached else None
    db = SimpleNamespace(
        fetchone=AsyncMock(return_value=entry),
        insert=AsyncMock(),
        update=AsyncMock(),
    )
    monkeypatch.setattr(crud, "db", db)
    client = httpx.AsyncClient
    requests = []

    def respond(request):
        requests.append(str(request.url))
        return httpx.Response(200, json={"fastestFee": 12})

    def make_client(**kwargs):
        assert kwargs["follow_redirects"] is False
        return client(transport=httpx.MockTransport(respond), **kwargs)

    monkeypatch.setattr(crud.httpx, "AsyncClient", make_client)
    gerty = SimpleNamespace(
        mempool_endpoint="http://127.0.0.1/internal#",
        time=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    assert await crud.get_mempool_info("fees_recommended", gerty) == {"fastestFee": 12}
    assert requests == ["https://mempool.space/api/v1/fees/recommended"]
    assert db.fetchone.call_args.args[1]["mempool_endpoint"] == crud.MEMPOOL_ENDPOINT
    stored = (db.update if cached else db.insert).call_args.args[1]
    assert stored.mempool_endpoint == crud.MEMPOOL_ENDPOINT


@pytest.mark.asyncio
async def test_writes_replace_custom_endpoint(monkeypatch):
    db = SimpleNamespace(insert=AsyncMock(), update=AsyncMock())
    monkeypatch.setattr(crud, "db", db)
    data = dict(
        name="Test",
        type="Gerty",
        utc_offset=0,
        refresh_time=300,
        wallet="wallet",
        lnbits_wallets="[]",
        exchange="USD",
        urls="[]",
        display_preferences="{}",
        mempool_endpoint="http://127.0.0.1",
    )
    created = await crud.create_gerty(CreateGerty.parse_obj(data))
    assert created.mempool_endpoint == crud.MEMPOOL_ENDPOINT
    updated = await crud.update_gerty(Gerty.parse_obj({"id": "existing", **data}))
    assert updated.mempool_endpoint == crud.MEMPOOL_ENDPOINT
