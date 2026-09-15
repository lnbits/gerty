import asyncio
from types import SimpleNamespace

from .. import helpers


def lightning_areas(monkeypatch, previous=None):
    data = {
        "latest": {
            "channel_count": 120,
            "node_count": 60,
            "total_capacity": 200000000,
            "avg_capacity": 1500000,
        }
    }
    if previous is not None:
        data["previous"] = previous

    async def fetch(*_):
        return data

    monkeypatch.setattr(helpers, "get_mempool_info", fetch)
    return asyncio.run(helpers.get_lightning_stats(SimpleNamespace(type="Gerty")))


def test_latest_only(monkeypatch):
    areas = lightning_areas(monkeypatch)
    assert len(areas) == 4
    assert all(len(area) == 2 for area in areas)
    assert [area[1]["value"] for area in areas] == [
        "120",
        "60",
        "2.0 BTC",
        "1,500,000 sats",
    ]


def test_available_comparison_uses_previous_baseline(monkeypatch):
    areas = lightning_areas(monkeypatch, {"channel_count": 100})
    assert areas[0][2]["value"] == "+20.0% in last 7 days"
    assert all(len(area) == 2 for area in areas[1:])


def test_zero_and_null_history(monkeypatch):
    areas = lightning_areas(monkeypatch, {"channel_count": 0, "node_count": None})
    assert all(len(area) == 2 for area in areas)
