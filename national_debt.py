"""Official federal debt observations, shared source caches and native displays."""

import asyncio
import csv
from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from time import monotonic

import httpx
from PIL import Image, ImageColor, ImageDraw, ImageFont

from .rendering import BOLD_FONT, FONT

TREASURY_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/"
    "fiscal_service/v2/accounting/od/debt_to_penny"
)
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def parse_daily(payload):
    points = {}
    for row in payload["data"]:
        day = date.fromisoformat(row["record_date"])
        value = Decimal(row["tot_pub_debt_out_amt"])
        if not value.is_finite() or value <= 0:
            raise ValueError("Invalid Treasury observation")
        points[day] = value
    if not points:
        raise ValueError("Empty Treasury response")
    return sorted(points.items())


def parse_history(content, series):
    points = {}
    for row in csv.DictReader(StringIO(content)):
        raw = row[series]
        if raw in ("", "."):
            continue
        day = date.fromisoformat(row.get("observation_date") or row["DATE"])
        value = Decimal(raw)
        if not value.is_finite() or value <= 0:
            raise ValueError("Invalid FRED observation")
        if day >= date(1971, 1, 1):
            points[day] = float(value)
    if len(points) < 2:
        raise ValueError("Insufficient FRED history")
    return sorted(points.items())


class DebtCache:
    """Cache each source independently; retry failures after five minutes."""

    def __init__(self):
        self.entries = {}
        self.locks = {
            key: asyncio.Lock() for key in ("daily", "GFDEBTN", "GFDEGDQ188S")
        }

    async def get(self, key, client):
        async with self.locks[key]:
            entry = self.entries.get(key)
            if entry and monotonic() < entry["retry_at"]:
                return entry["points"], entry["stale"]
            try:
                if key == "daily":
                    response = await client.get(
                        TREASURY_URL,
                        params={
                            "sort": "-record_date",
                            "page[size]": 45,
                            "fields": "record_date,tot_pub_debt_out_amt",
                        },
                    )
                    response.raise_for_status()
                    points = parse_daily(response.json())
                else:
                    response = await client.get(
                        FRED_URL, params={"id": key, "cosd": "1971-01-01"}
                    )
                    response.raise_for_status()
                    points = parse_history(response.text, key)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, ArithmeticError):
                points = entry["points"] if entry else []
                self.entries[key] = {
                    "points": points,
                    "stale": True,
                    "retry_at": monotonic() + 300,
                }
                return points, True
            self.entries[key] = {
                "points": points,
                "stale": False,
                "retry_at": monotonic() + (3600 if key == "daily" else 86400),
            }
            return points, False


_cache = DebtCache()


def daily_stats(points):
    if not points:
        return {}
    day, total = points[-1]
    cutoff = day - timedelta(days=30)
    baseline = next((point for point in reversed(points) if point[0] <= cutoff), None)
    previous = points[-2] if len(points) > 1 else None
    return {
        "recent": [
            (points[i][0], points[i][1], points[i][1] - points[i - 1][1])
            for i in range(len(points) - 1, max(0, len(points) - 6), -1)
        ],
        "date": day,
        "total": total,
        "daily_change": total - previous[1] if previous else None,
        "previous_date": previous[0] if previous else None,
        "month_change": total - baseline[1] if baseline else None,
        "baseline_date": baseline[0] if baseline else None,
    }


async def get_national_debt_data():
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        daily, nominal, ratio = await asyncio.gather(
            *(_cache.get(key, client) for key in ("daily", "GFDEBTN", "GFDEGDQ188S"))
        )
    return {
        **daily_stats(daily[0]),
        "nominal": nominal[0],
        "ratio": ratio[0],
        "stale": any(item[1] for item in (daily, nominal, ratio)),
    }


def money(value, *, signed=False):
    if value is None:
        return "Unavailable"
    prefix = ("+" if value >= 0 else "-") if signed else ""
    value = abs(value)
    for divisor, suffix in ((10**12, "T"), (10**9, "B"), (10**6, "M")):
        if value >= divisor:
            return f"{prefix}${value / divisor:.2f}{suffix}"
    return f"{prefix}${value:.2f}"


def quarter(day):
    return f"Q{(day.month - 1) // 3 + 1} {day.year}"


def render_national_debt(data, *, width=960, height=540, mode="L", theme="Orange Pill"):
    """Reference-inspired debt total, recent observations and history since 1971."""
    small = width <= 240
    readable = width == 480 and height == 320
    scale = 1 if small else min(width / 480, height / 272)
    w, h = width / scale, height / scale
    mono = mode == "L"
    palette = {
        "background": "#FFFFFF" if mono else "#050505",
        "text": "#111111" if mono else "#EEEEF0",
        "muted": "#555555" if mono else "#C0C0C8" if readable else "#A0A0AA",
        "border": "#DDDDDD" if mono else "#222226",
        "total": "#111111" if mono else "#1BC565",
        "up": "#111111" if mono else "#FF465C",
        "down": "#111111" if mono else "#1BC565",
    }
    image = Image.new("RGB", (width, height), palette["background"])
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=12, role="text", anchor="lt", bold=False):
        if readable:
            size = max(size, 18)
        draw.text(
            (round(x * scale), round(y * scale)),
            str(value),
            fill=palette[role],
            anchor=anchor,
            font=ImageFont.truetype(
                str(BOLD_FONT if bold else FONT), round(size * scale)
            ),
        )

    def line(coords, role="border"):
        draw.line(
            tuple(round(v * scale) for v in coords),
            fill=palette[role],
            width=max(1, round(scale)),
        )

    def change_role(value):
        return "muted" if value is None or value == 0 else "up" if value > 0 else "down"

    text(
        w / 2,
        9,
        "US National Debt",
        16 if small else 20 if readable else 18,
        "muted",
        "mt",
    )
    total = data.get("total")
    headline = f"${total:,.0f}" if total is not None else "Unavailable"
    size = 48 if not small else 28
    while (
        draw.textlength(
            headline, font=ImageFont.truetype(str(BOLD_FONT), round(size * scale))
        )
        > width - 20 * scale
    ):
        size -= 1
    text(w / 2, 32, headline, size, "total", "mt", True)
    text(
        w / 2,
        64 if small else 78 if readable else 80,
        f"Treasury reported: {data.get('date') or 'unavailable'}",
        10,
        "muted",
        "mt",
    )
    ratio = data.get("ratio", [])
    ratio_label = (
        f"{ratio[-1][1]:.1f}% ({quarter(ratio[-1][0])})" if ratio else "Unavailable"
    )
    text(
        w / 2,
        78 if small else 98 if readable else 94,
        f"Debt / GDP: {ratio_label}",
        11,
        "text",
        "mt",
    )
    recent = data.get("recent", [])
    table_y = 96 if small else 123 if readable else 114
    text(w / 2, table_y, "Latest Treasury updates", 11, "muted", "mt")
    count = 2 if small or readable else (5 if h >= 310 else 3)
    table_left, table_right = (
        (12, w - 12) if small or readable else (w * 0.22, w * 0.78)
    )
    for i, (day, value, change) in enumerate(recent[:count]):
        y = table_y + (21 + i * 23 if readable else 15 + i * 14)
        if i == 0:
            draw.rectangle(
                (
                    table_left * scale,
                    (y - 2) * scale,
                    table_right * scale,
                    (y + (19 if readable else 12)) * scale,
                ),
                fill=palette["border"],
            )
        text(table_left + 4, y, day.strftime("%b %d"), 11, "muted")
        text(w / 2 + 17, y, f"${value / Decimal(10**12):.3f}T", 11, anchor="rt")
        text(
            table_right - 4,
            y,
            money(change, signed=True),
            11,
            change_role(change),
            "rt",
        )
    if not recent:
        text(w / 2, table_y + 17, "Updates unavailable", 11, "muted", "mt")
    chart_title_y = 194 if readable else max(table_y + 17 + count * 14, h * 0.66)
    change = data.get("month_change")
    text(
        w / 2,
        chart_title_y,
        f"30-day change: {money(change, signed=True)}",
        11,
        change_role(change),
        "mt",
    )
    if readable:
        text(12, 216, "Debt since 1971 ($T)", 16, "muted")
    else:
        text(
            w / 2, chart_title_y + 13, "Nominal debt since 1971 ($T)", 11, "muted", "mt"
        )
    points = data.get("nominal", [])
    left, right = 32, w - 12
    top, bottom = (253, h - 39) if readable else (chart_title_y + 39, h - 27)
    if points:
        start, end = date(1971, 1, 1), points[-1][0]
        span = max(1, (end - start).days)
        ceiling = max(5, ((int(max(v for _, v in points) / 1e6) // 10) + 1) * 10)

        def x(day):
            return left + (day - start).days / span * (right - left)

        coords = [
            (x(day), bottom - value / 1e6 / ceiling * (bottom - top))
            for day, value in points
        ]
        mask = Image.new("L", (width, height))
        ImageDraw.Draw(mask).polygon(
            [
                (round(px * scale), round(py * scale))
                for px, py in [(left, bottom), *coords, (right, bottom)]
            ],
            fill=255,
        )
        shade = Image.new("RGB", (width, height), palette["background"])
        shade_draw = ImageDraw.Draw(shade)
        base = ImageColor.getrgb(palette["background"])
        tint = (160, 160, 160) if mono else (110, 12, 30)
        for row in range(round(top * scale), round(bottom * scale) + 1):
            alpha = (1 - (row / scale - top) / max(1, bottom - top)) * 0.65
            colour = tuple(
                round(b + (t - b) * alpha) for b, t in zip(base, tint, strict=True)
            )
            shade_draw.line((0, row, width, row), fill=colour)
        image.paste(shade, (0, 0), mask)
        for value in (0, ceiling):
            y = bottom - value / ceiling * (bottom - top)
            text(left - 4, y, str(value), 9, "muted", "rm")
            line((left, y, right, y))
        draw.line(
            [(round(px * scale), round(py * scale)) for px, py in coords],
            fill=palette["up"],
            width=max(1, round(1.5 * scale)),
        )
        for year, anchor in ((1971, "lt"), (2000, "mt"), (end.year, "rt")):
            text(x(date(year, 1, 1)), bottom + 3, str(year), 9, "muted", anchor)
        marker = x(date(1971, 8, 15))
        line((marker, top, marker, bottom), "muted")
        text(
            left + 3,
            top - (20 if readable else 12),
            "Aug 1971: gold convertibility suspended",
            9,
            "muted",
        )
        if not small:
            text(
                right,
                216 if readable else chart_title_y + 13,
                quarter(end),
                9,
                "muted",
                "rt",
            )
    else:
        text(w / 2, top, "History unavailable", 11, "muted", "mt")
    status = " | Refresh failed" if data.get("stale") else ""
    text(
        w / 2,
        h - (17 if readable else 10),
        f"Sources: Treasury / FRED{status}",
        9,
        "muted",
        "mt",
    )
    if mono:
        image = image.convert("L").point([round(v / 17) * 17 for v in range(256)])
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()
