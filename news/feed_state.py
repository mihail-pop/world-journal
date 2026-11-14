"""Compact metadata shared by the feed cache and scheduler."""
from django.utils import timezone

METADATA_FIELDS = (
    "fetched_at", "last_success_at", "last_attempt_at", "last_error",
    "last_error_detail", "retry_after_at", "consecutive_failures",
)


def snapshot_metadata(snapshot):
    metadata = {field: snapshot.get(field) for field in METADATA_FIELDS}
    items = snapshot.get("items")
    metadata["item_count"] = len(items) if isinstance(items, list) else None
    metadata["saved_at"] = timezone.now().isoformat()
    return metadata


def is_feed_key(key):
    return key.startswith("news:v") and any(part in key for part in (":google_country:", ":rss:", ":youtube:"))
