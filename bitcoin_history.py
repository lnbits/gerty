"""Annual Bitcoin anniversaries from the bundled calendar."""

import json
from functools import lru_cache
from pathlib import Path
from textwrap import shorten


@lru_cache(maxsize=1)
def load_events():
    return json.loads(Path(__file__).with_name("bitcoin_hisory.json").read_text())[
        "events"
    ]


def events_on(day):
    return [
        event for event in load_events() if event["month_day"] == day.strftime("%m-%d")
    ]


def history_screen(events, now, refresh):
    # Give every anniversary a turn without adding extra page slots.
    index = int(now.timestamp() // refresh) % len(events)
    event = events[index]
    excerpt = shorten(event["description"].split("\n\n")[0], width=340, placeholder="…")
    label = now.strftime("%d %B")
    if len(events) > 1:
        label += f" · {index + 1}/{len(events)}"
    return {
        "title": "Bitcoin History",
        "areas": [
            [
                {"value": event["title"], "size": 28},
                {"value": excerpt, "size": 23},
                {"value": label, "size": 18},
            ]
        ],
    }
