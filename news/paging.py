"""Search and paging helpers for saved news; no feed downloads or cache writes."""
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json

from django.db.models import Q
from django.utils.dateparse import parse_datetime


def search_query(params):
    return " ".join(str(params.get("q", "")).split())[:200]


def search_terms(query):
    return query.casefold().split()[:12]


def search_archive(rows, query):
    for term in search_terms(query):
        rows = rows.filter(Q(title__icontains=term) | Q(publisher__icontains=term) | Q(summary__icontains=term))
    return rows


def paging_time(params):
    now = datetime.now(UTC)
    try:
        stamp = parse_datetime(str(params.get("at", "")))
    except ValueError:
        stamp = None
    if stamp is not None:
        stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
        if now - timedelta(days=90) <= stamp <= now:
            return stamp
    return now


def result_version(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:20]


def page_changed(request, version):
    return request.headers.get("X-News-Paging") == "1" and bool(request.GET.get("v")) and request.GET["v"] != version
