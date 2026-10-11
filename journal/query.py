from datetime import date
from uuid import UUID

from django.db.models import Q
from django.db.models.functions import Substr

from .models import Entry, EntryType


def filtered_entries(params, *, for_display=True):
    entries = Entry.objects.all()
    if for_display:
        entries = entries.select_related("collection").prefetch_related("countries").annotate(excerpt=Substr("body", 1, 1600)).defer("body")
    query = params.get("q", "").strip()[:300]
    if query:
        entries = entries.filter(Q(title__icontains=query) | Q(body__icontains=query) | Q(source_name__icontains=query) | Q(source_url__icontains=query) | Q(sections__title__icontains=query) | Q(sections__body__icontains=query) | Q(sections__source_url__icontains=query)).distinct()
    country_codes = [code.upper() for code in params.getlist("country") if len(code) == 2]
    if country_codes:
        entries = entries.filter(countries__code__in=country_codes).distinct()
    collection = params.get("collection", "")
    if collection == "unfiled":
        entries = entries.filter(collection__isnull=True)
    elif collection:
        try:
            entries = entries.filter(collection_id=UUID(collection))
        except ValueError:
            entries = entries.none()
    entry_type = params.get("type", "")
    if entry_type == "mixed":
        entry_type = EntryType.NOTE
    if entry_type in EntryType.values:
        entries = entries.filter(entry_type=entry_type)
    if params.get("favorite") == "1":
        entries = entries.filter(is_favorite=True)
    if params.get("pinned") == "1":
        entries = entries.filter(is_pinned=True)
    if params.get("untagged") == "1":
        entries = entries.filter(countries__isnull=True)
    if params.get("undated") == "1":
        entries = entries.filter(event_date__isnull=True)
    date_field = "created_at__date" if params.get("date_basis") == "created" else "event_date"
    day = params.get("date", "")
    if day:
        try:
            entries = entries.filter(**{date_field: date.fromisoformat(day)})
        except ValueError:
            entries = entries.none()
    else:
        year, month = params.get("year", ""), params.get("month", "")
        if year:
            try:
                number = int(year)
                if not 1 <= number <= 9999:
                    raise ValueError
                entries = entries.filter(**{f"{date_field}__year": number})
            except ValueError:
                entries = entries.none()
        if month:
            try:
                number = int(month)
                if not 1 <= number <= 12:
                    raise ValueError
                entries = entries.filter(**{f"{date_field}__month": number})
            except ValueError:
                entries = entries.none()
    ordering = ("-is_pinned", "-created_at", "-id") if date_field.startswith("created") else ("-is_pinned", "-event_date", "-created_at", "-id")
    return entries.order_by(*ordering) if for_display else entries.order_by()
