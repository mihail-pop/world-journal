import re

from django.conf import settings
from django.core.exceptions import ValidationError


def parse_gap(value):
    if not value:
        return None
    match = re.fullmatch(r"\s*([0-9]{1,5})\s*(?:[-–—]|to)\s*([0-9]{1,5})\s*", value, re.IGNORECASE)
    if match:
        gap = [int(part) for part in match.groups()]
        if valid_gap(gap):
            return gap
    raise ValidationError("Enter two seconds values from 1 to 86400, in order, such as 60–65.")


def valid_gap(gap):
    return (isinstance(gap, list) and len(gap) == 2 and all(type(value) is int for value in gap)
            and 1 <= gap[0] <= gap[1] <= 86400)


def validate_pacing(value):
    if not isinstance(value, dict) or not value.keys() <= {"fixed", "maximum", "adaptive_token"}:
        raise ValidationError("Invalid Google News request gaps.")
    if any(not valid_gap(value[key]) for key in ("fixed", "maximum") if key in value):
        raise ValidationError("Invalid Google News request gaps.")
    if "adaptive_token" in value:
        token = value["adaptive_token"]
        if not isinstance(token, str) or not re.fullmatch(r"[0-9a-f]{32}", token):
            raise ValidationError("Invalid Google News pacing reset.")


def maximum_gap(pacing):
    upper = settings.NEWS_GOOGLE_MAX_REQUEST_SPACING_SECONDS
    return tuple(pacing.get("maximum") or (upper - settings.NEWS_GOOGLE_REQUEST_SPACING_STEP_SECONDS, upper))


def gap_label(gap):
    return f"{gap[0]}–{gap[1]}" if gap else ""
