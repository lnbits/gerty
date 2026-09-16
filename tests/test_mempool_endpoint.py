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
