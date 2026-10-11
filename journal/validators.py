import re
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator


validate_source_url = URLValidator(schemes=["http", "https"])
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
MAX_TIMESTAMP = 2_147_483_647


def validate_video_id(value):
    if value and not VIDEO_ID.fullmatch(value):
        raise ValidationError("Enter a valid 11-character YouTube video ID.")


def parse_youtube_reference(value):
    """Accept an ID or a known watch/short/embed URL, never an arbitrary embed."""
    value = value.strip()
    if VIDEO_ID.fullmatch(value):
        return value, None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
    except ValueError as error:
        raise ValidationError("Enter a valid YouTube video URL.") from error
    if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
        raise ValidationError("Enter a YouTube video ID or a YouTube video URL.")
    query = parse_qs(parsed.query)
    parts = parsed.path.strip("/").split("/")
    if host in {"youtu.be", "www.youtu.be"} and len(parts) == 1:
        video_id = parts[0]
    elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}:
        if parsed.path == "/watch":
            video_id = query.get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "embed", "live"}:
            video_id = parts[1]
        else:
            video_id = ""
    else:
        video_id = ""
    if not VIDEO_ID.fullmatch(video_id):
        raise ValidationError("This URL does not contain a valid YouTube video ID.")
    start = query.get("t", query.get("start", [""]))[0]
    seconds = None
    if start:
        if start.isdecimal():
            seconds = int(start)
        else:
            match = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?", start)
            if match and any(match.groups()):
                hours, minutes, secs = (int(part or 0) for part in match.groups())
                seconds = hours * 3600 + minutes * 60 + secs
        if seconds is None or seconds > MAX_TIMESTAMP:
            raise ValidationError("The video start time must be a nonnegative number of seconds.")
    return video_id, seconds
