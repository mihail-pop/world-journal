import json
from datetime import UTC
from hashlib import sha256

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Max
from django.http import HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from core.database import database_write, write_transaction
from core.views import render_page
from countries.models import Country

from .formatting import referenced_countries, render_body
from .forms import AttachmentForm, CollectionForm, EntryForm, SectionFormSet
from .models import Attachment, Collection, Entry, EntryType
from .query import filtered_entries
from .statistics import statistics_context
from .validators import VIDEO_ID


@never_cache
@require_http_methods(["GET", "POST"])
def player_video(request, video_id):
    if not VIDEO_ID.fullmatch(video_id):
        return JsonResponse({"message": "Choose a valid YouTube video."}, status=400)
    if request.method == "POST":
        if request.POST.get("favorite") not in {"true", "false"}:
            return JsonResponse({"message": "Choose a favorite state."}, status=400)
        favorite = request.POST["favorite"] == "true"
        initial = initial_entry(request, request.POST)
        with write_transaction():
            entry = Entry.objects.filter(youtube_video_id=video_id).first()
            if entry is None and favorite:
                entry = Entry.objects.create(
                    title=(request.POST.get("title", "").strip() or "YouTube video")[:300],
                    source_name=request.POST.get("channel", "YouTube")[:200],
                    entry_type=EntryType.YOUTUBE,
                    youtube_video_id=video_id,
                    source_url=f"https://www.youtube.com/watch?v={video_id}",
                    source_published_at=initial.get("source_published_at"),
                    is_favorite=True,
                )
            elif entry is not None and entry.is_favorite != favorite:
                entry.is_favorite = favorite
                entry.save(update_fields=["is_favorite", "updated_at"])
            if entry is not None and favorite:
                entry.countries.add(*initial["countries"])
    else:
        entry = Entry.objects.filter(youtube_video_id=video_id).first()
    return JsonResponse({
        "favorite": bool(entry and entry.is_favorite),
        "edit_url": reverse("journal:edit", args=[entry.pk]) if entry else None,
    })


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
    if request.GET:
        return navigate(request, reverse("journal:list") + "?" + request.GET.urlencode())
    latest = Entry.objects.order_by("-updated_at", "-id").values_list("pk", flat=True).first()
    return navigate(request, reverse("journal:edit", args=[latest]) if latest else reverse("journal:new"))


@never_cache
@require_http_methods(["GET"])
def list_entries(request):
    entries = filtered_entries(request.GET)
    params = request.GET.copy()
    params.pop("page", None)
    params.pop("v", None)
    signature = json.dumps(sorted(params.lists()), separators=(",", ":"))
    query_signature = sha256(signature.encode()).hexdigest()[:20]
    summary = filtered_entries(params, for_display=False).values("pk", "updated_at").aggregate(
        total=Count("pk", distinct=True), latest=Max("updated_at"))
    version = sha256(f"{query_signature}:{summary['total']}:{summary['latest']}".encode()).hexdigest()[:20]
    is_paging = request.headers.get("X-Journal-Paging") == "1"
    if is_paging and request.GET.get("v") and request.GET["v"] != version:
        return HttpResponse(status=409)
    paginator = Paginator(entries, 30)
    paginator.count = summary["total"]
    entries_page = paginator.get_page(request.GET.get("page"))
    refresh_url = reverse("journal:list") + ("?" + params.urlencode() if params else "")
    next_url = ""
    if entries_page.has_next():
        next_params = params.copy()
        next_params["page"], next_params["v"] = str(entries_page.next_page_number()), version
        next_url = reverse("journal:list") + "?" + next_params.urlencode()
    context = {
        "entries_page": entries_page, "paging_version": version, "query_signature": query_signature,
        "refresh_url": refresh_url, "next_url": next_url,
    }
    if is_paging:
        context["total_entries"] = summary["total"] or Entry.objects.exists()
        return render(request, "journal/partials/entry_results.html", context)
    context.update({
        "collections": Collection.objects.annotate(entry_count=Count("entries")),
        "unfiled_count": Entry.objects.filter(collection__isnull=True).count(),
        "countries": Country.objects.all(),
        "entry_types": EntryType.choices,
        "filters": request.GET,
        "selected_countries": [code.upper() for code in request.GET.getlist("country")],
        "total_entries": Entry.objects.count(),
    })
    return page(request, "core/partials/journal.html", context)


@require_http_methods(["GET"])
def statistics(request):
    params = QueryDict(mutable=True)
    params.update({"date_basis": "created", "period": "month", "stats_page": request.GET.get("stats_page", "1")})
    context = statistics_context(params)
    context["summary"][0]["label"] = "All entries"
    return page(request, "journal/statistics.html", context)


def initial_entry(request, parameters=None):
    parameters = request.GET if parameters is None else parameters
    initial = {"entry_type": parameters.get("type") if parameters.get("type") in EntryType.values else EntryType.NOTE}
    for field, parameter in (("title", "title"), ("source_url", "url"), ("source_name", "source"), ("youtube_reference", "video")):
        if value := parameters.get(parameter):
            limit = {"title": 300, "source_name": 200}.get(field)
            initial[field] = value[:limit] if limit else value
    initial["countries"] = list(Country.objects.filter(code__in=[c.upper() for c in parameters.getlist("country")]).values_list("pk", flat=True))
    collection = parameters.get("collection", "")
    if collection:
        try:
            initial["collection"] = Collection.objects.get(pk=collection)
        except (Collection.DoesNotExist, ValidationError):
            pass
    if published := parameters.get("published"):
        try:
            moment = parse_datetime(published)
            if moment:
                initial["source_published_at"] = moment.astimezone(UTC) if moment.tzinfo else moment
        except ValueError:
            pass
    return initial


@require_http_methods(["POST"])
def quick_save(request):
    if request.POST.get("type") not in {EntryType.ARTICLE, EntryType.YOUTUBE}:
        return JsonResponse({"message": "Choose an article or video to save."}, status=422)
    initial = initial_entry(request, request.POST)
    data = QueryDict(mutable=True)
    for field in ("title", "entry_type", "source_url", "source_name", "youtube_reference"):
        data[field] = initial.get(field, "")
    if moment := initial.get("source_published_at"):
        data["source_published_at"] = moment.strftime("%Y-%m-%dT%H:%M:%S")
    data.setlist("countries", [str(pk) for pk in initial["countries"]])
    form = EntryForm(data)
    if not form.is_valid():
        message = next(iter(form.errors.values()))[0]
        return JsonResponse({"message": str(message)}, status=422)
    content = form.instance
    if content.entry_type == EntryType.YOUTUBE and not content.youtube_video_id:
        return JsonResponse({"message": "This video has no valid YouTube ID."}, status=422)
    if content.entry_type == EntryType.ARTICLE and not content.source_url:
        return JsonResponse({"message": "This article has no valid source link."}, status=422)
    with write_transaction():
        # Repeated quick saves reuse the original entry without changing notes.
        lookup = {"youtube_video_id": content.youtube_video_id} if content.youtube_video_id else {"source_url": content.source_url}
        entry = Entry.objects.filter(**lookup).first()
        created = entry is None
        if created:
            entry = form.save()
        else:
            entry.countries.add(*form.cleaned_data["countries"])
    return JsonResponse({"edit_url": reverse("journal:edit", args=[entry.pk]), "created": created})


def section_submission(data, entry):
    """Rebuild the formset's initial/extra boundary after in-place autosaves.

    Existing IDs, rather than an outdated browser management count, determine
    which forms update rows. Keep the original prefixes for the JSON response.
    """
    data = data.copy()
    try:
        total = int(data.get("sections-TOTAL_FORMS", "0"))
    except ValueError:
        return data, {}
    if not 0 <= total <= 200:
        return data, {}
    ids = set(str(pk) for pk in entry.sections.values_list("pk", flat=True)) if not entry._state.adding else set()
    indices = list(range(total))
    initial = [index for index in indices if data.get(f"sections-{index}-id") in ids]
    order = initial + [index for index in indices if index not in initial]
    result = data.copy()
    for key in list(result):
        if key.startswith("sections-") and key.split("-", 2)[1].isdigit():
            del result[key]
    prefixes = {}
    for index, old_index in enumerate(order):
        old, new = f"sections-{old_index}-", f"sections-{index}-"
        prefixes[f"sections-{index}"] = f"sections-{old_index}"
        for key in data:
            if key.startswith(old):
                result.setlist(new + key[len(old):], data.getlist(key))
        if old_index not in initial:
            result[new + "id"] = ""
    result["sections-INITIAL_FORMS"] = str(len(initial))
    return result, prefixes


def save_entry(form, sections):
    with write_transaction():
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
    return entry


@require_http_methods(["POST"])
def autosave(request, pk):
    # The editor gets its UUID before its first save. Retrying that first save
    # updates the same entry instead of creating another draft.
    entry = Entry.objects.filter(pk=pk).first() or Entry(pk=pk)
    data = request.POST.copy()
    if not data.get("title", "").strip():
        data["title"] = "Untitled"
    section_data, prefixes = section_submission(data, entry)
    for prefix in prefixes:
        if section_data.get(prefix + "-DELETE"):
            continue
        if not section_data.get(prefix + "-title", "").strip():
            if any(section_data.get(prefix + "-" + field, "").strip() for field in ("body", "source_url", "youtube_reference", "source_name", "source_published_at", "youtube_start_seconds")):
                section_data[prefix + "-title"] = "Untitled section"
            elif not section_data.get(prefix + "-id"):
                section_data[prefix + "-DELETE"] = "on"
    form = EntryForm(data, instance=entry)
    sections = SectionFormSet(section_data, instance=entry, prefix="sections")
    form_valid, sections_valid = form.is_valid(), sections.is_valid()
    if not form_valid or not sections_valid:
        errors = []
        field_errors = {}
        for bound in (form, *sections.forms):
            if getattr(bound, "cleaned_data", {}).get("DELETE"):
                continue
            for field, messages in bound.errors.items():
                label = bound.fields[field].label or field.replace("_", " ").title() if field in bound.fields else "Entry"
                errors.extend(f"{label}: {error}" for error in messages)
                if field in bound.fields:
                    prefix = prefixes.get(bound.prefix, bound.prefix)
                    name = f"{prefix}-{field}" if prefix else field
                    field_errors[name] = [str(error) for error in messages]
        errors.extend(str(error) for error in sections.non_form_errors())
        return JsonResponse({"message": "Not saved: " + (errors[0] if errors else "Complete the highlighted fields."), "errors": field_errors}, status=422)
    entry = save_entry(form, sections)
    section_ids = {prefixes.get(section.prefix, section.prefix): {"id": str(section.instance.pk), "title": section.instance.title} for section in sections.forms if not section.instance._state.adding and not section.cleaned_data.get("DELETE")}
    return JsonResponse({"edit_url": reverse("journal:edit", args=[entry.pk]), "read_url": entry.get_absolute_url(), "title": entry.title, "sections": section_ids, "countries": list(entry.countries.values_list("pk", flat=True))})


@require_http_methods(["GET", "POST"])
def edit(request, pk=None):
    if pk:
        entry = get_object_or_404(Entry, pk=pk)
    elif request.method == "POST":
        # Share the editor's UUID with ordinary submissions too. A lost
        # autosave response followed by Save must not create a duplicate.
        try:
            draft_id = Entry._meta.pk.to_python(request.POST.get("entry_id"))
        except (ValidationError, ValueError):
            draft_id = None
        entry = Entry.objects.filter(pk=draft_id).first() if draft_id else None
        entry = entry or (Entry(pk=draft_id) if draft_id else Entry())
    else:
        entry = Entry()
    form = EntryForm(request.POST if request.method == "POST" else None, instance=entry, initial=initial_entry(request) if not pk else None)
    section_data = section_submission(request.POST, entry)[0] if request.method == "POST" else None
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
            entry = save_entry(form, sections)
            messages.success(request, "Saved.")
            return navigate(request, reverse("journal:edit", args=[entry.pk]))
    return page(request, "journal/edit.html", {"entry": entry, "form": form, "section_formset": sections, "is_new": entry._state.adding})


@require_http_methods(["GET"])
def detail(request, pk):
    entry = get_object_or_404(Entry.objects.select_related("collection").prefetch_related("countries", "sections__attachments", "attachments__section"), pk=pk)
    return page(request, "journal/detail.html", {"entry": entry, "main_attachments": [image for image in entry.attachments.all() if not image.section_id], "attachment_form": AttachmentForm(entry=entry)})


@require_http_methods(["GET", "POST"])
def delete_entry(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with write_transaction():
            entry.delete()
        messages.success(request, "Entry deleted, including its sections and local images.")
        return navigate(request, reverse("core:journal"))
    return page(request, "journal/confirm_delete.html", {"form": form, "title": f"Delete {entry.title}?", "description": "This deletes the entry, its subsections and its local images.", "cancel_url": entry.get_absolute_url()})


@require_http_methods(["GET", "POST"])
def collection_edit(request, pk=None):
    collection = get_object_or_404(Collection, pk=pk) if pk else Collection()
    form = CollectionForm(request.POST if request.method == "POST" else None, instance=collection)
    if request.method == "POST" and form.is_valid():
        with database_write():
            collection = form.save()
        messages.success(request, "Collection saved.")
        return navigate(request, reverse("journal:list") + f"?collection={collection.pk}")
    return page(request, "journal/collection_edit.html", {"form": form, "collection": collection, "is_new": pk is None})


@require_http_methods(["GET", "POST"])
def collection_delete(request, pk):
    collection = get_object_or_404(Collection, pk=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with database_write():
            collection.delete()
        messages.success(request, "Collection deleted. Its entries are kept in the journal.")
        return navigate(request, reverse("journal:list"))
    return page(request, "journal/confirm_delete.html", {"form": form, "title": f"Delete collection {collection.name}?", "description": "Entries are kept and moved to Unfiled. Only the collection is removed.", "cancel_url": reverse("journal:list") + f"?collection={collection.pk}"})


@require_http_methods(["POST"])
def upload_attachment(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    form = AttachmentForm(request.POST, request.FILES, entry=entry)
    if form.is_valid():
        form.save()
        messages.success(request, "Image added to the entry.")
        return navigate(request, entry.get_absolute_url())
    return page(request, "journal/detail.html", {"entry": entry, "main_attachments": entry.attachments.filter(section__isnull=True), "attachment_form": form})


@require_http_methods(["GET", "POST"])
def delete_attachment(request, pk, attachment_pk):
    attachment = get_object_or_404(Attachment.objects.select_related("entry"), pk=attachment_pk, entry_id=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    url = attachment.entry.get_absolute_url()
    if request.method == "POST" and form.is_valid():
        with write_transaction():
            attachment.delete()
        messages.success(request, "Image deleted.")
        return navigate(request, url)
    return page(request, "journal/confirm_delete.html", {"form": form, "title": "Delete this image?", "description": "The uploaded image will be removed from local storage.", "cancel_url": url})


@require_http_methods(["POST"])
def preview(request):
    body_format = request.POST.get("body_format", "markdown")
    return HttpResponse(render_body(request.POST.get("body", ""), body_format), content_type="text/html")
