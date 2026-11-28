"""Compact metadata shared by the feed cache and scheduler."""
import re

from django.utils import timezone

from .models import CustomSource

CUSTOM_FEED_ID = re.compile(r"custom_([a-f0-9]{32})(?:_feed)?\Z")

METADATA_FIELDS = (
    "fetched_at", "last_success_at", "last_attempt_at", "last_error",
    "last_error_detail", "retry_after_at", "failed_at", "server_retry_at",
    "google_spacing_seconds", "google_spacing_max_seconds", "google_request_ready_at",
)


def snapshot_metadata(snapshot):
    metadata = {field: snapshot.get(field) for field in METADATA_FIELDS}
    items = snapshot.get("items")
    metadata["item_count"] = len(items) if isinstance(items, list) else None
    metadata["saved_at"] = timezone.now().isoformat()
    return metadata


def is_feed_key(key):
    return key.startswith("news:v") and any(part in key for part in (":google_country:", ":rss:", ":youtube:"))


def feed_source_exists(source_id):
    match = CUSTOM_FEED_ID.fullmatch(source_id)
    return match is None or CustomSource.objects.filter(pk=match[1]).exists()
