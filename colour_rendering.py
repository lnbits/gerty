"""Native RGB layouts for landscape and square colour displays."""

import re
from datetime import datetime, timezone
from io import BytesIO
from math import ceil

from PIL import Image, ImageDraw, ImageFont

from .display_settings import COLOUR_THEMES
from .rendering import BOLD_FONT, FONT, SCREEN_TITLES, SINGLE_STATS


def render_colour_screen(
    data, slug, updated, theme="Orange Pill", *, height=320, width=480
):
    palette = COLOUR_THEMES[theme]
    image = Image.new("RGB", (width, height), palette["background"])
    compact = width <= 240
    draw = ImageDraw.Draw(image)

    def text(x, y, value, size=20, colour="text", bold=False, anchor="lt"):
        font = ImageFont.truetype(str(BOLD_FONT if bold else FONT), size)
        draw.text((x, y), str(value), font=font, fill=palette[colour], anchor=anchor)

    def card(box):
        draw.rounded_rectangle(
            box, radius=5, fill=palette["surface"], outline=palette["border"]
        )
        draw.line(
            (box[0] + 6, box[1] + 1, box[2] - 6, box[1] + 1),
            fill=palette["accent"],
            width=2,
        )

    def fit(items, box, centred=True):
        left, top, right, bottom = box
        width, height = right - left, bottom - top
        factor = 1.0
        while True:
            lines = []
            for value, size, colour, bold in items:
                font = ImageFont.truetype(
                    str(BOLD_FONT if bold else FONT), max(12, int(size * factor))
                )
                line = ""
                for word in str(value).replace("\n", " ").split():
                    candidate = (line + " " + word).strip()
                    if draw.textlength(candidate, font=font) <= width:
                        line = candidate
                    else:
                        if line:
                            lines.append((line, font, colour))
                        line = ""
                        for char in word:
                            if line and draw.textlength(line + char, font=font) > width:
                                lines.append((line, font, colour))
                                line = ""
                            line += char
                if line:
                    lines.append((line, font, colour))
            heights = [
                draw.textbbox((0, 0), line, font=font, anchor="lt")[3]
                for line, font, _ in lines
            ]
            total = sum(heights) + max(0, len(lines) - 1) * 6
            if total <= height or factor < 0.4:
                break
            factor *= 0.9
        y = top + max(0, (height - total) / 2)
        for (line, font, colour), line_height in zip(lines, heights, strict=True):
            if y + line_height > bottom:
                break
            draw.text(
                ((left + right) / 2 if centred else left, y),
                line,
                font=font,
                fill=palette[colour],
                anchor="mt" if centred else "lt",
            )
            y += line_height + 6

    title = (
        "Block explorer"
        if slug == "block_explorer"
        else SCREEN_TITLES.get(slug) or data.get("title") or "Bitcoin statistics"
    )
    title_size = 22 if compact else 26
    while (
        draw.textlength(title, font=ImageFont.truetype(str(BOLD_FONT), title_size))
        > width - 24
        and title_size > 12
    ):
        title_size -= 1
    text(12, 9, title, title_size, "accent", True)
    text(
        width - 12,
        height - 16,
        f"Updated {updated}",
        14 if compact else 16,
        "muted",
        anchor="rt",
    )

    if slug == "block_explorer":
        if compact:
            _square_block_dashboard(data, draw, text, card, palette)
        else:
            _block_dashboard(data, draw, text, card, palette, height)
    else:
        areas = data["areas"] or [[{"value": "No data available", "size": 20}]]
        if slug == "mempool_recommended_fees" and len(areas[0]) == 10:
            source = areas[0]
            areas = [[source[i], source[i + 4]] for i in range(2, 6)]
        columns = 2 if len(areas) > 1 else 1
        rows = ceil(len(areas) / columns)
        content_height = height - 64
        for i, area in enumerate(areas):
            cell_width = (width - 8) / columns
            left = 8 + (i % columns) * cell_width
            top = 40 + (i // columns) * (content_height / rows)
            right = left + cell_width - 8
            bottom = top + content_height / rows - 8
            card((left, top, right, bottom))
            items = []
            for j, item in enumerate(area):
                value = str(item["value"]).replace("\n", " ")
                if slug == "bitcoin_history":
                    size, colour, bold = (
                        (24, "accent", True)
                        if j == 0
                        else (21, "text", False) if j == 1 else (16, "muted", False)
                    )
                elif slug == "fun_satoshi_quotes":
                    size, colour, bold = (
                        (23, "text", False) if j == 0 else (19, "secondary", False)
                    )
                elif j == 0:
                    size, colour, bold = 22, "muted", True
                    value = value.removesuffix("'s Wallet")
                elif j == 1:
                    size, colour, bold = (
                        (100 if slug in SINGLE_STATS else 42),
                        "accent",
                        False,
                    )
                    if len(value) > 22:
                        size = 28
                    if slug == "url_checker":
                        colour = "positive" if value.startswith("2") else "negative"
                else:
                    size, colour, bold = 18, "muted", False
                value = re.sub(r"\bCurrent\s+", "", value)
                if (
                    compact
                    and j == 1
                    and slug not in {"fun_satoshi_quotes", "bitcoin_history"}
                ):
                    # Keep numerical readings on one line in narrow dashboard cards.
                    while (
                        size > 12
                        and draw.textlength(
                            value, font=ImageFont.truetype(str(FONT), size)
                        )
                        > right - left - 12
                    ):
                        size -= 1
                items.append((value, size, colour, bold))
            fit(
                items,
                (
                    left + (6 if compact else 12),
                    top + (6 if compact else 12),
                    right - (6 if compact else 12),
                    bottom - (6 if compact else 12),
                ),
                slug not in {"fun_satoshi_quotes", "bitcoin_history"},
            )
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _square_block_dashboard(data, draw, text, card, palette):
    """Use stacked panels and a compact fee row on the 1.3-inch display."""
    from .block_explorer import smooth_points

    card((8, 36, 232, 91))
    for i, target in enumerate((144, 6, 3, 1)):
        x = 36 + i * 56
        rate = data["estimates"].get(str(target))
        text(x, 42, f"{target} blk", 12, "muted", anchor="mt")
        text(
            x,
            58,
            f"{rate:.1f}" if rate is not None else "N/A",
            18,
            "accent",
            anchor="mt",
        )
    text(224, 87, "sat/vB", 10, "muted", anchor="rb")
    card((8, 97, 232, 173))
    values = list(reversed(data["intervals"]))
    average = sum(v for _, v in values) / len(values) if values else None
    text(16, 103, "Block intervals", 16, "text", True)
    text(
        224,
        104,
        f"{average:.1f}m" if average is not None else "N/A",
        14,
        "muted",
        anchor="rt",
    )
    high = max(15, max((v for _, v in values), default=0))
    target_y = 164 - 10 / high * 40
    draw.line((16, target_y, 224, target_y), fill=palette["border"])
    points = [
        (16 + i * 208 / max(1, len(values) - 1), 164 - max(0, v) / high * 40)
        for i, (_, v) in enumerate(values)
    ]
    if len(points) > 1:
        draw.line(smooth_points(points), fill=palette["accent"], width=2)
    for x, y in points:
        draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=palette["accent"])
    card((8, 179, 232, 218))
    blocks = data["blocks"]
    tip = f"#{blocks[0]['height']}" if blocks else "No blocks"
    total = sum(size for _, size in data["histogram"]) / 1000000
    text(16, 186, tip, 16, "accent", True)
    text(16, 203, "Chain tip", 11, "muted")
    text(224, 186, f"{total:.2f} MvB", 16, "text", anchor="rt")
    text(224, 203, "Mempool", 11, "muted", anchor="rt")


def _block_dashboard(data, draw, text, card, palette, height=320):
    from .block_explorer import smooth_points

    # Match the e-paper layout: fee estimates and recent blocks share one row.
    now = datetime.now(timezone.utc).timestamp()
    for i, target in enumerate((144, 6, 3, 1)):
        left = 4 + i * 59
        card((left, 38, left + 55, 92))
        text(
            left + 27,
            44,
            str(target),
            13,
            "muted",
            True,
            "mt",
        )
        rate = data["estimates"].get(str(target))
        text(
            left + 27,
            62,
            f"{rate:.1f}" if rate is not None else "N/A",
            14,
            "accent",
            anchor="mt",
        )
        text(left + 27, 78, "sat/vB", 8, "muted", anchor="mt")
    for i, block in enumerate(data["blocks"][:4]):
        # Leave breathing room around the chain-tip divider.
        left = 9 + (i + 4) * 59
        card((left, 38, left + 55, 92))
        text(left + 27, 44, f"#{block['height']}", 12, "text", True, "mt")
        age = max(0, int((now - block["timestamp"]) / 60))
        text(left + 27, 63, f"{age}m", 13, "muted", anchor="mt")
        text(left + 27, 78, "ago", 8, "muted", anchor="mt")
    # Divider marks the chain tip between fee targets and recent blocks.
    # Keep the chain-tip marker the same height as the cards, with breathing
    # room above and below instead of extending into the chart panels.
    draw.line((240, 31, 240, 99), fill=palette["secondary"], width=2)
    lower_top, lower_bottom = 112, height - 24
    card((8, lower_top, 236, lower_bottom))
    card((244, lower_top, 472, lower_bottom))
    text(18, 121, "Block intervals", 22, "text", True)
    text(254, 121, "Mempool fees", 22, "text", True)
    values = list(reversed(data["intervals"]))
    low = min(0, min((v for _, v in values), default=0))
    high = max(15, max((v for _, v in values), default=10))
    chart_top, chart_bottom = 174, lower_bottom - 34
    for y in (chart_top, (chart_top + chart_bottom) / 2, chart_bottom):
        draw.line((34, y, 224, y), fill=palette["border"])
        draw.line((268, y, 458, y), fill=palette["border"])
    target_y = chart_bottom - (10 - low) / (high - low) * (chart_bottom - chart_top)
    for x in range(34, 224, 10):
        draw.line((x, target_y, x + 5, target_y), fill=palette["secondary"])
    points = [
        (
            34 + i * 190 / max(1, len(values) - 1),
            chart_bottom - (v - low) / (high - low) * (chart_bottom - chart_top),
        )
        for i, (_, v) in enumerate(values)
    ]
    if len(points) > 1:
        draw.line(smooth_points(points), fill=palette["accent"], width=2)
    for x, y in points:
        draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=palette["accent"])
    average = sum(v for _, v in values) / len(values) if values else None
    text(
        18,
        145,
        f"Avg {average:.1f} min" if average is not None else "No history",
        17,
        "muted",
    )
    text(28, chart_top, f"{high:.0f}", 14, "muted", anchor="rt")
    text(28, chart_bottom - 8, f"{low:.0f}", 14, "muted", anchor="rt")
    if values:
        text(34, chart_bottom + 11, values[0][0], 15, "muted")
        text(224, chart_bottom + 11, values[-1][0], 15, "muted", anchor="rt")
    edges = (1, 2, 5, 10, 50, float("inf"))
    bins = [0.0] * len(edges)
    for rate, size in data["histogram"]:
        for i, edge in enumerate(edges):
            if rate < edge:
                bins[i] += size / 1000000
                break
    total = sum(bins)
    text(254, 145, f"{total:.2f} MvB", 17, "muted")
    maximum = max(max(bins), 1)
    for i, size in enumerate(bins):
        x = 270 + i * 32
        if size:
            draw.rectangle(
                (
                    x,
                    chart_bottom - size / maximum * (chart_bottom - chart_top),
                    x + 21,
                    chart_bottom,
                ),
                fill=palette["accent"],
            )
        text(
            x + 10,
            chart_bottom + 11,
            ("<1", "1-2", "2-5", "5-10", "10-50", "50+")[i],
            12,
            "muted",
            anchor="mt",
        )
    text(460, lower_bottom - 5, "sat/vB", 12, "muted", anchor="rb")
