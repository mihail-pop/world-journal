"""Search and paging helpers for saved news; no feed downloads or cache writes."""
from datetime import UTC, datetime
from hashlib import sha256
import json
import re

from django.core import signing
from django.db.models import BooleanField, Q
from django.db.models.expressions import RawSQL
from django.utils.dateparse import parse_datetime


def search_query(params):
    return " ".join(str(params.get("q", "")).split())[:200]


def search_terms(query):
    return query.casefold().split()[:12]


def search_archive(rows, query):
    trigrams = {}
    for term in search_terms(query):
        rows = rows.filter(Q(title__icontains=term) | Q(publisher__icontains=term) | Q(summary__icontains=term))
        if len(term) >= 3 and not any(ord(char) < 32 for char in term):
            trigrams.update(dict.fromkeys(term[index:index + 3] for index in range(len(term) - 2)))
    if not trigrams:
        return rows
    # The compact index stores three-character tokens. Intersect those tokens,
    # then verify the complete substrings above to retain existing search rules.
    match = " AND ".join('"' + token.replace('"', '""') + '"' for token in trigrams)
    matches = "SELECT rowid FROM news_archive_search WHERE news_archive_search MATCH %s"
    candidates = rows.filter(search_id__in=RawSQL(matches, [match]))
    small = list(candidates.order_by().values_list("pk", flat=True)[:257])
    if len(small) <= 256:
        return rows.filter(pk__in=small)
    # For broad matches, let the date/views index supply the next page. A direct
    # search_id lookup would read and sort every matching article first.
    return rows.filter(RawSQL(f"(news_archivednews.search_id + 0) IN ({matches})", [match], output_field=BooleanField()))


class NewsCursorError(ValueError):
    pass


def encode_cursor(values, query):
    return signing.dumps({**values, "query": query}, salt="news-pagination", compress=True)


def decode_cursor(token, query):
    if not token:
        return None
    try:
        if len(token) > 2048:
            raise ValueError()
        values = signing.loads(token, salt="news-pagination")
        if not isinstance(values, dict) or values.get("query") != query:
            raise ValueError()
        return values
    except (signing.BadSignature, ValueError, TypeError) as error:
        raise NewsCursorError("This news page is no longer valid. Refresh the results.") from error


def cursor_date(date, identity):
    if not isinstance(identity, str) or not re.fullmatch(r"[a-f0-9]{64}", identity):
        raise NewsCursorError("Invalid news cursor.")
    if date is None:
        return None
    moment = parse_datetime(date) if isinstance(date, str) else None
    if moment is None or moment.tzinfo is None:
        raise NewsCursorError("Invalid news cursor.")
    return moment


def archive_page(rows, cursor, limit, *, sort="newest", date_field="published_at"):
    """Seek through indexed ranges, including date/view ties and NULLs.

    Separate ranges avoid OR predicates that can make SQLite walk every
    preceding row even with a keyset cursor. No OFFSET or total count is used.
    """
    columns = ("identity", date_field, "view_count")
    date_order = ("-" + date_field, "identity")
    result = []

    def take(query, ordering):
        remaining = limit - len(result)
        if remaining > 0:
            result.extend(query.order_by(*ordering).values_list(*columns)[:remaining])

    def dates(query, position=None):
        if position:
            identity, stamp = position.get("identity"), position.get("published")
            moment = cursor_date(stamp, identity)
            if moment is None:
                take(query.filter(**{date_field + "__isnull": True, "identity__gt": identity}), ("identity",))
                return
            take(query.filter(**{date_field: moment, "identity__gt": identity}), ("identity",))
            take(query.filter(**{date_field + "__lt": moment}), date_order)
        else:
            take(query.filter(**{date_field + "__isnull": False}), date_order)
        if date_field == "published_at":
            take(query.filter(published_at__isnull=True), ("identity",))

    if sort not in {"views", "least_views"}:
        dates(rows, cursor)
        return result
    ascending = sort == "least_views"
    view_order = (("view_count" if ascending else "-view_count"), *date_order)
    if not cursor:
        take(rows.filter(view_count__isnull=False), view_order)
        dates(rows.filter(view_count__isnull=True))
    elif cursor.get("views") is None:
        dates(rows.filter(view_count__isnull=True), cursor)
    else:
        views = cursor["views"]
        if type(views) is not int or not 0 <= views <= 9223372036854775807:
            raise NewsCursorError("Invalid news cursor.")
        dates(rows.filter(view_count=views), cursor)
        take(rows.filter(**{"view_count__gt" if ascending else "view_count__lt": views}), view_order)
        dates(rows.filter(view_count__isnull=True))
    return result


def paging_time(params):
    now = datetime.now(UTC)
    try:
        stamp = parse_datetime(str(params.get("at", "")))
    except ValueError:
        stamp = None
    if stamp is not None:
        stamp = stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)
        if datetime(1970, 1, 1, tzinfo=UTC) <= stamp <= now:
            return stamp
    return now


def result_version(value):
    return sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()[:20]


def page_changed(request, version):
    return request.headers.get("X-News-Paging") == "1" and bool(request.GET.get("v")) and request.GET["v"] != version
