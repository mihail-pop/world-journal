"""Choose one timezone for the shared app, without changing stored instants."""
import os
import sys
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.core.exceptions import ImproperlyConfigured


def app_timezone_name():
    configured = os.environ.get("TZ", "").strip()
    if configured:
        try:
            return ZoneInfo(configured).key
        except (ValueError, ZoneInfoNotFoundError) as error:
            raise ImproperlyConfigured("TZ must be an IANA timezone, such as Europe/Bucharest or UTC.") from error
    if sys.platform == "win32":
        from tzlocal import get_localzone_name

        try:
            return ZoneInfo(get_localzone_name()).key
        except (OSError, LookupError, ValueError):
            return "UTC"
    return "UTC"
