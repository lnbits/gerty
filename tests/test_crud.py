from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from .. import crud
from ..models import Gerty


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "wallet_ids,expected",
    [
        ("wallet", {"w0": "wallet"}),
        (["first", "second"], {"w0": "first", "w1": "second"}),
        (["x') OR 1=1 --"], {"w0": "x') OR 1=1 --"}),
    ],
)
async def test_wallet_ids_bound_as_parameters(monkeypatch, wallet_ids, expected):
    fetchall = AsyncMock(return_value=[])
    monkeypatch.setattr(crud, "db", SimpleNamespace(fetchall=fetchall))
    assert await crud.get_gertys(wallet_ids) == []
    placeholders = ", ".join(f":{key}" for key in expected)
    fetchall.assert_awaited_once_with(
        f"SELECT * FROM gerty.gertys WHERE wallet IN ({placeholders})",
        expected,
        model=Gerty,
    )


@pytest.mark.asyncio
async def test_empty_wallet_list_skips_query(monkeypatch):
    fetchall = AsyncMock()
    monkeypatch.setattr(crud, "db", SimpleNamespace(fetchall=fetchall))
    assert await crud.get_gertys([]) == []
    fetchall.assert_not_awaited()
