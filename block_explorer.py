"""Live block explorer data and the e-paper dashboard that displays it."""

import asyncio
import math
from datetime import datetime, timezone
from importlib import import_module
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

from .rendering import BOLD_FONT, FONT, panel, stipple


async def get_block_explorer_data():
    # Lazy imports let the other Gerty screens work on older LNbits versions.
    from lnbits.settings import settings

    if not getattr(settings, "lnbits_blockexplorer_enabled", False):
        raise ValueError("Enable Block explorer in LNbits settings.")
    blockexplorer = import_module("lnbits.core.services.blockexplorer")
    tip, fees, blocks = await asyncio.wait_for(
        asyncio.gather(
            blockexplorer.fetch_tip(),
            blockexplorer.fetch_fee_estimates(),
            blockexplorer.fetch_recent_blocks(count=10),
        ),
        timeout=30,
    )
    return prepare_data(tip.dict(), fees.dict(), [block.dict() for block in blocks])


def prepare_data(tip, fees, blocks):
    """Normalize the API models; fee estimates are BTC/kB, histogram is sat/vB."""
    height = int(tip["height"])
    recent = sorted(
        {int(b["height"]): b for b in blocks if int(b["height"]) <= height}.values(),
        key=lambda b: b["height"],
        reverse=True,
    )
    estimates = {}
    for target, rate in fees["estimates"].items():
        rate = float(rate)
        if math.isfinite(rate) and rate >= 0:
            estimates[str(target)] = rate * 100000
    histogram = []
    for entry in fees["histogram"]:
        rate, size = float(entry["fee_rate"]), float(entry["vsize"])
        if not math.isfinite(rate) or not math.isfinite(size) or rate < 0 or size < 0:
            raise ValueError("Invalid mempool histogram")
        histogram.append((rate, size))
    intervals = [
        (newer["height"], (newer["timestamp"] - recent[i + 1]["timestamp"]) / 60)
        for i, newer in enumerate(recent[:-1])
        if newer["height"] == recent[i + 1]["height"] + 1
    ]
    return {
        "height": height,
        "blocks": recent,
        "estimates": estimates,
        "histogram": histogram,
        "intervals": intervals,
    }


def smooth_points(points, steps=20):
    """Shape-preserving cubic interpolation through uniformly spaced samples."""
    if len(points) < 3:
        return points
    slopes = [points[i + 1][1] - point[1] for i, point in enumerate(points[:-1])]
    tangents = [slopes[0]]
    for i in range(1, len(points) - 1):
        before, after = slopes[i - 1], slopes[i]
        tangents.append(
            2 * before * after / (before + after) if before * after > 0 else 0
        )
    tangents.append(slopes[-1])
    curve = [points[0]]
    for i, (x, y) in enumerate(points[:-1]):
        end_x, end_y = points[i + 1]
        for sample in range(1, steps + 1):
            t = sample / steps
            value = (
                (2 * t**3 - 3 * t**2 + 1) * y
                + (t**3 - 2 * t**2 + t) * tangents[i]
                + (-2 * t**3 + 3 * t**2) * end_y
                + (t**3 - t**2) * tangents[i + 1]
            )
            # Roundoff on flat segments must not place pixels outside the data.
            value = min(max(value, min(y, end_y)), max(y, end_y))
            curve.append((x + t * (end_x - x), value))
    return curve


def render_block_explorer(data, updated, now=None):
    now = now if now is not None else datetime.now(timezone.utc).timestamp()
    image = Image.new("L", (960, 540), 255)
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=24, bold=False, anchor="lt"):
        font = ImageFont.truetype(str(BOLD_FONT if bold else FONT), size)
        draw.text((x, y), str(value), font=font, fill=0, anchor=anchor)

    text(14, 10, "Block explorer", 32, True)
    text(944, 14, f"Tip #{data['height']:,}", 24, anchor="rt")
    intervals = dict(data["intervals"])
    # Put the nearest confirmation target beside the latest mined block.
    draw.line((478, 42, 478, 179), fill=0, width=3)
    for index in range(8):
        left = 12 + index * 114 + (26 if index >= 4 else 0)
        panel(draw, (left, 45, left + 104, 174))
        centre = left + 52
        if index < 4:
            target = (144, 6, 3, 1)[index]
            text(
                centre,
                67,
                f"{target} block" + ("s" if target != 1 else ""),
                22,
                True,
                "mt",
            )
            rate = data["estimates"].get(str(target))
            text(
                centre,
                99,
                f"{rate:.1f}" if rate is not None else "N/A",
                30,
                anchor="mt",
            )
            text(centre, 139, "sat/vB", 22, anchor="mt")
        elif index - 4 < len(data["blocks"]):
            block = data["blocks"][index - 4]
            text(centre, 67, f"#{block['height']}", 22, True, "mt")
            age = (now - block["timestamp"]) / 60
            text(
                centre,
                96,
                f"{int(age)}m ago" if age >= 0 else "Future time",
                20,
                anchor="mt",
            )
            interval = intervals.get(block["height"])
            text(
                centre,
                124,
                f"{interval:.1f} min" if interval is not None else "N/A",
                23,
                anchor="mt",
            )
            text(centre, 148, "interval", 20, anchor="mt")
        else:
            text(centre, 99, "No block", 22, anchor="mt")

    panel(draw, (12, 190, 466, 500))
    panel(draw, (484, 190, 942, 500))
    text(26, 214, "Block intervals", 30, True)
    text(498, 214, "Mempool fee distribution", 28, True)
    values = list(reversed(data["intervals"]))
    average = sum(v for _, v in values) / len(values) if values else None
    text(
        26,
        244,
        (
            f"{average:.1f} min average  |  10 min target"
            if average is not None
            else "No interval history"
        ),
        22,
    )
    total = sum(size for _, size in data["histogram"]) / 1000000
    text(498, 244, f"{total:.2f} MvB in mempool", 24)

    def axes(left, top, right, bottom, minimum, maximum, unit):
        draw.line((left, top, left, bottom, right, bottom), fill=0, width=2)
        for tick in range(5):
            value = minimum + (maximum - minimum) * tick / 4
            y = bottom - (bottom - top) * tick / 4
            for x in range(left, right, 6):
                draw.point((x, y), fill=0)
            text(left - 7, y, f"{value:g}", 18, anchor="rm")
        text(left, top - 21, unit, 20)

    lo = min(0, math.floor(min((v for _, v in values), default=0) / 5) * 5)
    hi = max(15, math.ceil(max((v for _, v in values), default=10) / 5) * 5)
    axes(66, 297, 444, 442, lo, hi, "minutes")
    target_y = 442 - (10 - lo) / (hi - lo) * 145
    for x in range(66, 440, 14):
        draw.line((x, target_y, min(x + 8, 444), target_y), fill=0, width=2)
    points = [
        (66 + i * 378 / max(1, len(values) - 1), 442 - (v - lo) / (hi - lo) * 145)
        for i, (_, v) in enumerate(values)
    ]
    if len(points) > 1:
        draw.line(smooth_points(points), fill=0, width=3)
    for x, y in points:
        draw.rectangle((x - 3, y - 3, x + 3, y + 3), fill=0)
    if values:
        text(66, 452, values[0][0], 20)
        text(444, 452, values[-1][0], 20, anchor="rt")
    text(255, 477, "Block height", 22, anchor="mt")

    # Fixed, labelled ranges retain the high-fee tail without crushing low fees.
    edges = (1, 2, 3, 5, 10, 20, 50, float("inf"))
    labels = ("<1", "1-2", "2-3", "3-5", "5-10", "10-20", "20-50", "50+")
    bins = [0.0] * len(edges)
    for rate, size in data["histogram"]:
        for i, edge in enumerate(edges):
            if rate < edge:
                bins[i] += size / 1000000
                break
    maximum = max(1, math.ceil(max(bins)))
    axes(540, 297, 924, 442, 0, maximum, "MvB")
    for i, size in enumerate(bins):
        left = 545 + i * 47
        top = 442 - size / maximum * 145
        if size:
            draw.rectangle((left, top, left + 32, 442), fill=221, outline=0)
            stipple(draw, (left + 1, top + 1, left + 32, 441))
        text(left + 16, 453, labels[i], 16, anchor="mt")
    text(732, 477, "Fee rate (sat/vB)", 22, anchor="mt")
    text(944, 520, f"Updated {updated}", 20, anchor="rt")
    image = image.point([round(i / 17) * 17 for i in range(256)])
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
