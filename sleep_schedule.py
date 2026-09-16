"""Timezone-aware device sleep schedules stored with display preferences."""

import json
import math
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_schedule(preferences):
    schedule = preferences.get("_schedule", {})
    if not isinstance(schedule, dict):
        raise ValueError("Sleep schedule must be an object.")
    zone = schedule.get("timezone", "UTC")
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise ValueError("Select a valid timezone.") from exc
    if not isinstance(schedule.get("enabled", False), bool):
        raise ValueError("Enable Sleep Time must be true or false.")
    for field, default in (("sleep_time", "22:00"), ("wake_time", "06:00")):
        value = schedule.get(field, default)
        if not isinstance(value, str) or not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", value
        ):
            raise ValueError("Sleep and wake times must use HH:MM format.")
    if schedule.get("enabled") and schedule.get("sleep_time", "22:00") == schedule.get(
        "wake_time", "06:00"
    ):
        raise ValueError("Sleep time and wake time must be different.")
    return schedule


def local_time(gerty, now=None):
    now = now or datetime.now(timezone.utc)
    schedule = validate_schedule(json.loads(gerty.display_preferences))
    if "timezone" in schedule:
        return now.astimezone(ZoneInfo(schedule["timezone"]))
    # Preserve existing devices' clock settings until a timezone is selected.
    return now.astimezone(timezone(timedelta(hours=gerty.utc_offset or 0)))


def sleep_data(gerty, now=None):
    now = now or datetime.now(timezone.utc)
    preferences = json.loads(gerty.display_preferences)
    schedule = validate_schedule(preferences)
    if not schedule.get("enabled", False):
        return None
    local = local_time(gerty, now)
    start = schedule.get("sleep_time", "22:00")
    end = schedule.get("wake_time", "06:00")
    clock = local.strftime("%H:%M")
    sleeping = start <= clock < end if start < end else clock >= start or clock < end
    if not sleeping:
        return None
    hour, minute = map(int, end.split(":"))
    wake = local.replace(
        hour=hour, minute=minute, second=0, microsecond=0, fold=local.fold
    )
    if start > end and clock >= start:
        wake += timedelta(days=1)
    # Round-trip normalizes nonexistent spring-forward wall times.
    wake = wake.astimezone(timezone.utc).astimezone(local.tzinfo)
    seconds = max(1, math.ceil(wake.timestamp() - now.timestamp()))
    return {
        "schema_version": 1,
        "sleep_mode": True,
        "wake_at": wake.isoformat(),
        "sleep_seconds": seconds,
    }
