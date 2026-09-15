from io import BytesIO

import pytest
from PIL import Image

from ..block_explorer import prepare_data, render_block_explorer, smooth_points


def test_curve_preserves_measurements_without_overshooting():
    points = [(0, 10), (10, 80), (20, 20), (30, 20), (40, 100)]
    curve = smooth_points(points)
    assert curve[::20] == points
    for i in range(len(points) - 1):
        low, high = sorted((points[i][1], points[i + 1][1]))
        assert all(low <= y <= high for _, y in curve[i * 20 : (i + 1) * 20 + 1])


def test_units_and_chronological_intervals():
    data = prepare_data(
        {"height": 102},
        {
            "estimates": {"1": 0.000011, "3": -1},
            "histogram": [{"fee_rate": 2, "vsize": 1000000}],
        },
        [
            {"height": 100, "timestamp": 1000},
            {"height": 102, "timestamp": 2200},
            {"height": 101, "timestamp": 1600},
        ],
    )
    assert data["estimates"]["1"] == pytest.approx(1.1)
    assert "3" not in data["estimates"]
    assert data["histogram"] == [(2, 1000000)]
    assert data["intervals"] == [(102, 10), (101, 10)]
    assert data["blocks"][0]["height"] == 102


def test_missing_history_does_not_invent_intervals():
    data = prepare_data(
        {"height": 3},
        {"estimates": {}, "histogram": []},
        [{"height": 1, "timestamp": 100}, {"height": 3, "timestamp": 200}],
    )
    assert data["intervals"] == []


def test_live_png_and_small_histogram_bins():
    data = prepare_data(
        {"height": 100},
        {
            "estimates": {"1": 0.00001},
            "histogram": [
                {"fee_rate": 0.5, "vsize": 10000000},
                {"fee_rate": 100, "vsize": 1},
            ],
        },
        [],
    )
    png = render_block_explorer(data, "12:00", now=1000)
    image = Image.open(BytesIO(png))
    assert image.size == (960, 540)
    assert image.mode == "L"
    assert set(image.tobytes()) <= set(range(0, 256, 17))
    assert len(png) < 2 * 1024 * 1024
    data["height"] += 1
    assert render_block_explorer(data, "12:00", now=1000) != png
