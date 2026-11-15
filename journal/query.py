from datetime import date
from uuid import UUID

from django.db.models import Case, DateTimeField, F, Q, When
from django.db.models.functions import Coalesce, Lower, Substr

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
    sort = params.get("sort", "activity")
    if sort not in {"activity", "release", "title"}:
        sort = "activity"
    if sort == "release":
        entries = entries.annotate(journal_release_date=Case(
            When(entry_type=EntryType.NOTE, then=F("updated_at")),
            default=Coalesce("source_published_at", "updated_at"), output_field=DateTimeField(),
        ))
    if params.get("date_basis") in {"event", "created"}:
        date_field = "created_at__date" if params["date_basis"] == "created" else "event_date"
    else:
        date_field = "journal_release_date__date" if sort == "release" else "updated_at__date"
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
    field = Lower("title") if sort == "title" else F("journal_release_date" if sort == "release" else "updated_at")
    ordering = field.asc(nulls_last=True) if params.get("order") == "asc" else field.desc(nulls_last=True)
    return entries.order_by(ordering, "id") if for_display else entries.order_by()
