"""Annual Bitcoin anniversaries from the bundled calendar."""

import json
import re
from functools import lru_cache
from html import unescape
from pathlib import Path


@lru_cache(maxsize=1)
def load_events():
    return json.loads(Path(__file__).with_name("bitcoin_hisory.json").read_text())[
        "events"
    ]


def events_on(day):
    return [
        event for event in load_events() if event["month_day"] == day.strftime("%m-%d")
    ]


def display_description(event):
    description = event["description"]
    paragraphs = re.split(
        r"(?:\s*<br\s*/?>\s*){2,}|\n\s*\n",
        event.get("description_html", ""),
        flags=re.IGNORECASE,
    )
    for paragraph in paragraphs:
        if not re.search(r"<a\b", paragraph, re.IGNORECASE):
            continue
        remaining = re.sub(
            r"<a\b[^>]*>.*?</a>", "", paragraph, flags=re.IGNORECASE | re.DOTALL
        ).strip(" \n.|")
        prompt = re.match(
            r"^(Read\b|View\b|Watch\b|See\b|You can read\b|"
            r"The Bitcoin whitepaper can be viewed\b|This\s+documents\b|"
            r"The\s+that started\b)",
            remaining,
            re.IGNORECASE,
        )
        if remaining and not prompt:
            continue
        text = " ".join(unescape(re.sub(r"<[^>]+>", "", paragraph)).split())
        description = description.replace(text, "")
    return "\n\n".join(
        part.strip() for part in description.split("\n\n") if part.strip()
    )


def history_screen(events, now, refresh):
    # Give every anniversary a turn without adding extra page slots.
    index = int(now.timestamp() // refresh) % len(events)
    event = events[index]
    label = now.strftime("%d %B")
    if event.get("year") is not None:
        label += f" {event['year']}"
    if len(events) > 1:
        label += f" · {index + 1}/{len(events)}"
    return {
        "title": "Bitcoin History",
        "areas": [
            [
                {"value": event["title"], "size": 28},
                {"value": label, "size": 18},
                {"value": display_description(event), "size": 23},
            ]
        ],
    }
