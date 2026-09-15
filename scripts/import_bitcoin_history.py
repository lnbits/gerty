"""Import bitcoin.holiday's calendar, including its unfolded HTML descriptions."""

import argparse
import json
import re
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from zoneinfo import ZoneInfo


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def handle_starttag(self, tag, attrs):
        if tag in {"br", "p", "div"}:
            self.parts.append("\n")


def parse_calendar(source):
    events = []
    # Standard ICS folding; this export also has literal multiline descriptions.
    source = re.sub(r"\r?\n[ \t]", "", source)
    for block in source.split("BEGIN:VEVENT")[1:]:
        fields = {}
        key = None
        for line in block.split("END:VEVENT", 1)[0].splitlines():
            match = re.match(r"^([A-Z][A-Z0-9-]*)(?:;[^:]*)?:(.*)$", line)
            if match:
                key, value = match.groups()
                fields[key] = value
            elif key:
                fields[key] += "\n" + line
        start = fields["DTSTART"]
        # The supplied export encodes British local midnight as UTC (23:00 in BST).
        day = (
            datetime.strptime(start, "%Y%m%dT%H%M%SZ")
            .replace(tzinfo=ZoneInfo("UTC"))
            .astimezone(ZoneInfo("Europe/London"))
            .date()
        )
        description = fields.get("DESCRIPTION", "")
        description = re.sub(
            r"\\([nN,;\\])",
            lambda m: "\n" if m[1].lower() == "n" else m[1],
            description,
        )
        parser = PlainText()
        parser.feed(description)
        plain = "\n\n".join(
            " ".join(part.split())
            for part in re.split(r"\n\s*\n", "".join(parser.parts))
            if part.strip()
        )
        events.append(
            {
                "date": day.isoformat(),
                "month_day": day.strftime("%m-%d"),
                "title": fields["SUMMARY"],
                "description": plain,
                "description_html": description,
                "url": fields.get("URL", ""),
                "source_start": start,
            }
        )
    return {
        "source": "bitcoin.holiday",
        "calendar_timezone": "Europe/London",
        "recurrence": "annual",
        "events": events,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("calendar", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(
        json.dumps(
            parse_calendar(args.calendar.read_text()), indent=2, ensure_ascii=False
        )
        + "\n"
    )
