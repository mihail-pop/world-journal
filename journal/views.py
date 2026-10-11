import json
from datetime import UTC

from django import forms
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods

from core.views import render_page
from countries.models import Country

from .formatting import referenced_countries, render_body
from .forms import AttachmentForm, CollectionForm, EntryForm, SectionFormSet
from .models import Attachment, Collection, Entry, EntryType
from .query import filtered_entries
from .statistics import statistics_context


class ConfirmationForm(forms.Form):
    confirm = forms.BooleanField(label="I confirm this deletion.")


def navigate(request, url):
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse()
        response.headers["HX-Location"] = json.dumps({"path": url, "target": "#app-content", "swap": "innerHTML show:top"})
        return response
    return redirect(url)


def page(request, template, context):
    return render_page(request, "journal", page_template=template, context=context)


@require_http_methods(["GET"])
def index(request):
    entries = filtered_entries(request.GET)
    paginator = Paginator(entries, 30)
    params = request.GET.copy()
    params.pop("page", None)
    return page(request, "core/partials/journal.html", {
        "entries_page": paginator.get_page(request.GET.get("page")),
        "collections": Collection.objects.annotate(entry_count=Count("entries")),
        "unfiled_count": Entry.objects.filter(collection__isnull=True).count(),
        "countries": Country.objects.all(),
        "entry_types": EntryType.choices,
        "filters": request.GET,
        "selected_countries": [code.upper() for code in request.GET.getlist("country")],
        "pagination_query": params.urlencode(),
        "total_entries": Entry.objects.count(),
    })


@require_http_methods(["GET"])
def statistics(request):
    params = QueryDict(mutable=True)
    params.update({"date_basis": "created", "period": "month", "stats_page": request.GET.get("stats_page", "1")})
    context = statistics_context(params)
    context["summary"][0]["label"] = "All entries"
    return page(request, "journal/statistics.html", context)


def initial_entry(request):
    initial = {"entry_type": request.GET.get("type") if request.GET.get("type") in EntryType.values else EntryType.NOTE}
    for field, parameter in (("title", "title"), ("source_url", "url"), ("source_name", "source"), ("youtube_reference", "video")):
        if value := request.GET.get(parameter):
            limit = {"title": 300, "source_name": 200}.get(field)
            initial[field] = value[:limit] if limit else value
    initial["countries"] = list(Country.objects.filter(code__in=[c.upper() for c in request.GET.getlist("country")]).values_list("pk", flat=True))
    collection = request.GET.get("collection", "")
    if collection:
        try:
            initial["collection"] = Collection.objects.get(pk=collection)
        except (Collection.DoesNotExist, ValidationError):
            pass
    if published := request.GET.get("published"):
        try:
            moment = parse_datetime(published)
            if moment:
                initial["source_published_at"] = moment.astimezone(UTC) if moment.tzinfo else moment
        except ValueError:
            pass
    return initial


@require_http_methods(["GET", "POST"])
def edit(request, pk=None):
    entry = get_object_or_404(Entry, pk=pk) if pk else Entry()
    form = EntryForm(request.POST if request.method == "POST" else None, instance=entry, initial=initial_entry(request) if not pk else None)
    section_data = request.POST.copy() if request.method == "POST" else None
    adding_section = request.method == "POST" and request.POST.get("action") == "add_section"
    if adding_section:
        try:
            total = int(section_data.get("sections-TOTAL_FORMS", "0"))
            section_data["sections-TOTAL_FORMS"] = str(min(200, total + 1))
        except ValueError:
            pass
    sections = SectionFormSet(section_data, instance=entry, prefix="sections")
    if request.method == "POST" and not adding_section:
        form_valid, sections_valid = form.is_valid(), sections.is_valid()
        if form_valid and sections_valid:
            with transaction.atomic():
                entry = form.save()
                sections.instance = entry
                section_objects = sections.save(commit=False)
                for section in sections.deleted_objects:
                    section.delete()
                for section in section_objects:
                    section.entry = entry
                    section.save()
                codes = referenced_countries(entry.body, entry.body_format)
                for section in entry.sections.all():
                    codes.update(referenced_countries(section.body, section.body_format))
                entry.countries.add(*Country.objects.filter(code__in=codes))
            return navigate(request, entry.get_absolute_url())
    return page(request, "journal/edit.html", {"entry": entry, "form": form, "section_formset": sections, "is_new": pk is None})


@require_http_methods(["GET"])
def detail(request, pk):
    entry = get_object_or_404(Entry.objects.select_related("collection").prefetch_related("countries", "sections__attachments", "attachments__section"), pk=pk)
    return page(request, "journal/detail.html", {"entry": entry, "main_attachments": [image for image in entry.attachments.all() if not image.section_id], "attachment_form": AttachmentForm(entry=entry)})


@require_http_methods(["GET", "POST"])
def delete_entry(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            entry.delete()
        return navigate(request, reverse("core:journal"))
    return page(request, "journal/confirm_delete.html", {"form": form, "title": f"Delete {entry.title}?", "description": "This deletes the entry, its subsections and its local images.", "cancel_url": entry.get_absolute_url()})


@require_http_methods(["GET", "POST"])
def collection_edit(request, pk=None):
    collection = get_object_or_404(Collection, pk=pk) if pk else Collection()
    form = CollectionForm(request.POST if request.method == "POST" else None, instance=collection)
    if request.method == "POST" and form.is_valid():
        collection = form.save()
        return navigate(request, reverse("core:journal") + f"?collection={collection.pk}")
    return page(request, "journal/collection_edit.html", {"form": form, "collection": collection, "is_new": pk is None})


@require_http_methods(["GET", "POST"])
def collection_delete(request, pk):
    collection = get_object_or_404(Collection, pk=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        collection.delete()
        return navigate(request, reverse("core:journal"))
    return page(request, "journal/confirm_delete.html", {"form": form, "title": f"Delete collection {collection.name}?", "description": "Entries are kept and moved to Unfiled. Only the collection is removed.", "cancel_url": reverse("core:journal") + f"?collection={collection.pk}"})


@require_http_methods(["POST"])
def upload_attachment(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    form = AttachmentForm(request.POST, request.FILES, entry=entry)
    if form.is_valid():
        form.save()
        return navigate(request, entry.get_absolute_url())
    return page(request, "journal/detail.html", {"entry": entry, "main_attachments": entry.attachments.filter(section__isnull=True), "attachment_form": form})


@require_http_methods(["GET", "POST"])
def delete_attachment(request, pk, attachment_pk):
    attachment = get_object_or_404(Attachment.objects.select_related("entry"), pk=attachment_pk, entry_id=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    url = attachment.entry.get_absolute_url()
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            attachment.delete()
        return navigate(request, url)
    return page(request, "journal/confirm_delete.html", {"form": form, "title": "Delete this image?", "description": "The uploaded image will be removed from local storage.", "cancel_url": url})


@require_http_methods(["POST"])
def preview(request):
    body_format = request.POST.get("body_format", "markdown")
    return HttpResponse(render_body(request.POST.get("body", ""), body_format), content_type="text/html")
