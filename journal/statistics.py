"""Database aggregates over the same filtered entry set as the journal list."""

from django.core.paginator import Paginator
from django.db.models import Count, F, Q
from django.db.models.functions import TruncDate, TruncMonth, TruncYear
from django.urls import reverse

from countries.models import Country

from .models import Entry, EntryType
from .query import filtered_entries


FILTER_KEYS = ("q", "country", "collection", "type", "date_basis", "date", "year", "month", "favorite", "pinned", "undated", "untagged")


def filter_params(params):
    result = params.copy()
    for key in list(result):
        if key not in FILTER_KEYS:
            result.pop(key)
    return result


def journal_link(params, **changes):
    result = filter_params(params)
    for key, value in changes.items():
        result[key] = str(value)
    query = result.urlencode()
    return reverse("journal:index") + (f"?{query}" if query else "")


def statistics_context(params):
    # A PK subquery isolates search/country joins from grouping. One entry counts
    # once even when several subsections match a search or several tags match.
    matching_ids = filtered_entries(params, for_display=False).values("pk")
    entries = Entry.objects.filter(pk__in=matching_ids).order_by()
    totals = entries.aggregate(
        total=Count("pk"), favorites=Count("pk", filter=Q(is_favorite=True)),
        pinned=Count("pk", filter=Q(is_pinned=True)),
        undated=Count("pk", filter=Q(event_date__isnull=True)),
    )
    totals["untagged"] = entries.filter(countries__isnull=True).count()
    summary = [
        {"label": "Matching entries", "count": totals["total"], "url": journal_link(params)},
        {"label": "Favorites", "count": totals["favorites"], "url": journal_link(params, favorite=1)},
        {"label": "Pinned", "count": totals["pinned"], "url": journal_link(params, pinned=1)},
        {"label": "Without event date", "count": totals["undated"], "url": journal_link(params, undated=1)},
        {"label": "Without country tags", "count": totals["untagged"], "url": journal_link(params, untagged=1)},
    ]
    type_counts = dict(entries.values_list("entry_type").annotate(count=Count("pk")))
    active_type = params.get("type")
    types = [
        {"label": label, "count": type_counts.get(value, 0), "url": journal_link(params, type=value)}
        for value, label in EntryType.choices if active_type not in EntryType.values or value == active_type
    ]
    country_counts = Country.objects.filter(journal_entries__pk__in=matching_ids)
    selected_codes = [code.upper() for code in params.getlist("country") if len(code) == 2]
    if selected_codes:
        # With an OR country filter, keep the breakdown to those tags. Replacing
        # that filter by a single row's country then reproduces its exact count.
        country_counts = country_counts.filter(pk__in=selected_codes)
    country_counts = country_counts.values("code", "name").annotate(count=Count("journal_entries", distinct=True)).order_by("-count", "name", "code")
    countries = [{"label": row["name"], "count": row["count"], "url": journal_link(params, country=row["code"])} for row in country_counts]
    collection_counts = entries.values("collection_id", "collection__name").annotate(count=Count("pk")).order_by("-count", "collection__name", "collection_id")
    collections = [
        {"label": row["collection__name"] or "Unfiled", "count": row["count"], "url": journal_link(params, collection=row["collection_id"] or "unfiled")}
        for row in collection_counts
    ]
    date_basis = "created" if params.get("date_basis") == "created" else "event"
    period = params.get("period", "month")
    period = period if period in {"day", "month", "year"} else "month"
    date_expression = TruncDate("created_at") if date_basis == "created" else F("event_date")
    dated = entries.annotate(stats_date=date_expression).filter(stats_date__isnull=False)
    period_expression = {"day": F("stats_date"), "month": TruncMonth("stats_date"), "year": TruncYear("stats_date")}[period]
    time_counts = dated.annotate(stats_period=period_expression).values("stats_period").annotate(count=Count("pk")).order_by("-stats_period")
    time_page = Paginator(time_counts, 50).get_page(params.get("stats_page"))
    time_rows = []
    for row in time_page:
        stamp = row["stats_period"]
        if period == "day":
            change = {"date": stamp.isoformat()}
            label = stamp.strftime("%b %d, %Y")
        elif period == "month":
            change = {"year": stamp.year, "month": stamp.month}
            label = stamp.strftime("%B %Y")
        else:
            change = {"year": stamp.year}
            label = str(stamp.year)
        time_rows.append({"label": label, "count": row["count"], "url": journal_link(params, **change)})
    pagination = filter_params(params)
    pagination["period"] = period
    return {
        "summary": summary, "types": types, "country_counts": countries,
        "collection_counts": collections, "time_rows": time_rows, "time_page": time_page,
        "statistics_pagination_query": pagination.urlencode(), "period": period,
        "date_basis": date_basis, "matching_count": totals["total"],
        "has_entries": bool(totals["total"]) or Entry.objects.exists(), "journal_url": journal_link(params),
        "countries_are_filtered": bool(selected_codes),
        "type_maximum": max((row["count"] for row in types), default=1) or 1,
        "country_maximum": max((row["count"] for row in countries), default=1) or 1,
        "collection_maximum": max((row["count"] for row in collections), default=1) or 1,
        "time_maximum": max((row["count"] for row in time_rows), default=1) or 1,
    }
