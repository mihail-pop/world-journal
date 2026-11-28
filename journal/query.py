from datetime import date, datetime, timedelta
from uuid import UUID

from django.db.models import Case, DateTimeField, F, Q, When
from django.db.models.functions import Coalesce, Lower, Substr
from django.utils import timezone

from .models import Entry, EntryType


SORT_FIELDS = {"activity": "updated_at", "release": "journal_release_date", "event": "event_date", "title": "title"}


def entry_sort(params):
    requested = params.get("sort")
    return requested if requested in SORT_FIELDS else "activity"


def date_bounds(params):
    if value := params.get("date"):
        start = date.fromisoformat(value)
        return start, start + timedelta(days=1) if start < date.max else None
    values = []
    for name, digits, maximum in (("year", 4, 9999), ("month", 2, 12), ("day", 2, 31)):
        value = params.get(name, "").strip()
        if value and (not value.isascii() or not value.isdigit() or len(value) > digits or not 1 <= int(value) <= maximum):
            raise ValueError("Enter a valid date.")
        values.append(int(value) if value else None)
    year, month, day = values
    today = timezone.localdate()
    if year is None and (month is not None or day is not None):
        year = today.year
    if month is None and day is not None:
        month = today.month
    if year is None:
        return None, None
    start = date(year, month or 1, day or 1)
    if day is not None:
        end = start + timedelta(days=1) if start < date.max else None
    elif month is not None and month < 12:
        end = date(year, month + 1, 1)
    else:
        end = date(year + 1, 1, 1) if year < 9999 else None
    return start, end


def date_boundary(value):
    return timezone.make_aware(datetime.combine(value, datetime.min.time()))


def filtered_entries(params, *, for_display=True, apply_date=True):
    entries = Entry.objects.all()
    if for_display:
        entries = entries.select_related("collection").prefetch_related("countries").annotate(excerpt=Substr("body_text", 1, 1600)).defer("body", "body_text")
    query = params.get("q", "").strip()[:300]
    if query:
        entries = entries.filter(Q(title__icontains=query) | Q(body_text__icontains=query) | Q(source_name__icontains=query) | Q(source_url__icontains=query) | Q(sections__title__icontains=query) | Q(sections__body_text__icontains=query) | Q(sections__source_url__icontains=query)).distinct()
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
    types = [EntryType.NOTE if value == "mixed" else value for value in params.getlist("type")]
    types = [value for value in types if value in EntryType.values]
    if types:
        entries = entries.exclude(entry_type__in=types) if params.get("filter_mode") == "exclude" else entries.filter(entry_type__in=types)
    if params.get("favorite") == "1":
        entries = entries.filter(is_favorite=True)
    if params.get("pinned") == "1":
        entries = entries.filter(is_pinned=True)
    if params.get("untagged") == "1":
        entries = entries.filter(countries__isnull=True)
    if params.get("undated") == "1":
        entries = entries.filter(event_date__isnull=True)
    sort = entry_sort(params)
    if sort == "release":
        entries = entries.annotate(journal_release_date=Case(
            When(entry_type=EntryType.NOTE, then=F("updated_at")),
            default=Coalesce("source_published_at", "updated_at"), output_field=DateTimeField(),
        ))
    if apply_date:
        try:
            start, end = date_bounds(params)
            if start is not None:
                entries = entries.filter(updated_at__gte=date_boundary(start))
            if end is not None:
                entries = entries.filter(updated_at__lt=date_boundary(end))
        except ValueError:
            entries = entries.none()
    field = Lower("title") if sort == "title" else F(SORT_FIELDS[sort])
    ordering = field.asc(nulls_last=True) if params.get("order") == "asc" else field.desc(nulls_last=True)
    return entries.order_by(ordering, "id") if for_display else entries.order_by()
