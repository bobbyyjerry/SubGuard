"""Convert the current UTC instant to an account's local calendar date."""
from datetime import datetime, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

DEFAULT_TIME_ZONE = "UTC"


def utc_now():
    return datetime.now(timezone.utc)


def local_date(zone_name=None, *, now=None):
    instant = utc_now() if now is None else now
    return instant.astimezone(ZoneInfo(zone_name or DEFAULT_TIME_ZONE)).date()


def today_for_user(user):
    preferences = user.preferences if user.is_authenticated else None
    return local_date(preferences.time_zone if preferences else None)


@lru_cache(maxsize=1)
def time_zone_names():
    return tuple(sorted(available_timezones()))
