"""Daily watched-wallet balances and an equaliser-style display."""

import colorsys
import json
from datetime import datetime, timedelta, timezone
from io import BytesIO
from math import ceil, floor, log10

from lnbits.core.crud import get_payments_history, get_wallet_for_key
from lnbits.core.models import PaymentFilters
from lnbits.db import Filter, Filters
from PIL import Image, ImageDraw, ImageFont

from .rendering import BOLD_FONT, FONT


async def get_wallet_history_data(gerty, now=None, *, invoice_key=None):
    """Use LNbits' fee-inclusive balance history, filling inactive UTC days."""
    today = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    days = [today - timedelta(days=29 - i) for i in range(30)]
    totals = [0] * len(days)
    seen = set()
    wallet_name = ""
    filters = Filters(
        filters=[
            Filter.parse_query(
                "time[ge]", [f"{days[0].isoformat()}T00:00:00+00:00"], PaymentFilters
            )
        ]
    )
    keys = [invoice_key] if invoice_key else json.loads(gerty.lnbits_wallets or "[]")
    for key in keys:
        wallet = await get_wallet_for_key(key=key)
        if wallet is None:
            raise ValueError("A watched wallet is unavailable.")
        if wallet.id in seen:
            continue
        seen.add(wallet.id)
        wallet_name = wallet.name
        history = await get_payments_history(
            wallet_id=wallet.id, group="day", filters=filters
        )
        history = sorted(history, key=lambda point: point.date)
        balance = (
            history[0].balance - history[0].income + history[0].spending
            if history
            else wallet.balance_msat
        )
        index = 0
        for i, day in enumerate(days):
            while index < len(history) and history[index].date.date() <= day:
                balance = history[index].balance
                index += 1
            totals[i] += balance
    return {
        "points": list(zip(days, [value / 1000 for value in totals], strict=True)),
        "wallet_count": len(seen),
        "wallet_name": wallet_name if len(seen) == 1 else "",
    }


def _label(value):
    for divisor, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "k")):
        if abs(value) >= divisor:
            return f"{value / divisor:.3g}{suffix}"
    return f"{value:g}"


def render_wallet_history(data, updated, *, width=480, height=320, mode="RGB"):
    """Native-size segmented bars with a mirrored, fading reflection."""
    mono = mode == "L"
    scale = 2 if width >= 900 else 1
    background = (255, 255, 255) if mono else (5, 7, 14)
    ink = (25, 25, 25) if mono else (235, 241, 255)
    muted = (85, 85, 85) if mono else (154, 167, 191)
    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)

    def text(
        x, y, value, size=14, fill: tuple[int, int, int] = ink, anchor="lt", bold=False
    ):
        draw.text(
            (x, y),
            str(value),
            fill=fill,
            anchor=anchor,
            font=ImageFont.truetype(str(BOLD_FONT if bold else FONT), size * scale),
        )

    text(12 * scale, 10 * scale, "Wallet history", 22, bold=True)
    name = data.get("wallet_name", "")
    if name:
        font = ImageFont.truetype(str(FONT), 12 * scale)
        while draw.textlength(name, font=font) > width - 24 * scale:
            name = name[:-2] + "…"
        text(12 * scale, 34 * scale, name, 12, muted)
    count = data["wallet_count"]
    text(width - 12 * scale, height - 8 * scale, f"Updated {updated}", 12, muted, "rb")
    if not count:
        text(width / 2, height / 2, "No wallets configured", 16, muted, "mm")
    else:
        _draw_chart(
            image,
            draw,
            text,
            data["points"],
            scale,
            mono,
            background,
            muted,
            bool(name),
        )
    if mono:
        image = image.convert("L").point(
            [round(value / 17) * 17 for value in range(256)]
        )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _draw_chart(image, draw, text, points, scale, mono, background, muted, named=False):
    width, height = image.size
    top, bottom = (73 if named else 57) * scale, int(height * 0.69)
    values = [value for _, value in points]
    magnitude = max([abs(value) for value in values] + [1])
    step = 10 ** floor(log10(magnitude))
    maximum = ceil(magnitude / step) * step
    minimum = -maximum if min(values, default=0) < 0 else 0
    ticks = (maximum, (maximum + minimum) / 2, minimum)
    font = ImageFont.truetype(str(FONT), 12 * scale)
    left = (
        ceil(max(draw.textlength(_label(value), font=font) for value in ticks))
        + 8 * scale
    )
    right = width - 5 * scale

    def y(value):
        return bottom - (value - minimum) / (maximum - minimum) * (bottom - top)

    zero = y(0)
    text(left, top - 19 * scale, "Balance (sats)", 12, muted)
    for value in ticks:
        line_y = y(value)
        draw.line(
            (left, line_y, right, line_y),
            fill=(210, 210, 210) if mono else (30, 36, 52),
        )
        text(left - 5 * scale, line_y, _label(value), 12, muted, "rm")
    draw.line((left, top, left, bottom), fill=muted)
    draw.line((left, zero, right, zero), fill=muted)
    bars = Image.new("RGB", image.size, background)
    bars_draw = ImageDraw.Draw(bars)
    pitch = (right - left) / max(1, len(points))
    for i, (_, value) in enumerate(points):
        rgb = colorsys.hsv_to_rgb(
            (0.78 + i / max(1, len(points) - 1) * 0.88) % 1, 0.86, 1
        )
        colour = (35, 35, 35) if mono else tuple(int(channel * 255) for channel in rgb)
        x1 = int(left + i * pitch + 2 * scale)
        x2 = max(x1, int(left + (i + 1) * pitch - scale))
        low, high = sorted((int(zero), int(y(value))))
        # Anchor every segment to zero so rows align across adjacent bars.
        direction = -1 if value >= 0 else 1
        for offset in range(0, high - low, 7 * scale):
            start = int(zero) + direction * offset
            end = int(zero) + direction * min(offset + 5 * scale - 1, high - low)
            box = (x1, min(start, end), x2, max(start, end))
            draw.rectangle(box, fill=colour)
            bars_draw.rectangle(box, fill=colour)
    reflection_height = max(1, height - bottom - 25 * scale)
    reflection = bars.crop((left, top, right, bottom)).transpose(
        Image.Transpose.FLIP_TOP_BOTTOM
    )
    reflection = reflection.resize((right - left, reflection_height))
    fade = Image.new("L", reflection.size)
    fade_draw = ImageDraw.Draw(fade)
    for row in range(reflection_height):
        fade_draw.line(
            (0, row, reflection.width, row),
            fill=int(100 * (1 - row / reflection_height) ** 2),
        )
    image.paste(reflection, (left, bottom + 3 * scale), fade)
    label_y = bottom + 7 * scale
    for index in sorted({0, len(points) // 2, len(points) - 1}):
        if not points:
            break
        position = left + (index + 0.5) * pitch
        label = points[index][0].strftime("%d %b")
        bounds = draw.textbbox((0, 0), label, font=font)
        tile = Image.new("RGBA", (bounds[2] + 2, bounds[3] - bounds[1] + 2))
        ImageDraw.Draw(tile).text((1, 1 - bounds[1]), label, font=font, fill=muted)
        tile = tile.rotate(45, expand=True, resample=Image.Resampling.BICUBIC)
        label_x = max(
            3 * scale,
            min(int(position - tile.width / 2), width - tile.width - 3 * scale),
        )
        image.paste(tile, (label_x, label_y), tile)
