import json
import logging
from datetime import UTC, date, timedelta
from hashlib import sha256

from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Count, Max
from django.db.models.functions import Lower
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.dateparse import parse_datetime
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import never_cache

from core.database import database_write, write_transaction
from core.views import render_page
from countries.models import Country

from .documents import image_ids, validate_document
from .formatting import country_aliases, referenced_countries
from .forms import AttachmentForm, CollectionForm, EntryForm, SectionFormSet, default_collection
from .models import Attachment, BodyFormat, BUILTIN_COLLECTION_NAMES, Collection, DeletedEntry, Entry, EntryType
from .query import date_boundary, date_bounds, entry_sort, filtered_entries
from .validators import VIDEO_ID, parse_youtube_reference
from .bookmarks import bookmark_details, bookmark_states


ENTRY_CONFLICT = "This entry changed or was deleted in another tab. Your draft is still here. Open the Journal in another tab to check the saved version."
IMAGE_UNDO_GRACE = timedelta(days=1)


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
                    collection=default_collection(EntryType.YOUTUBE),
                    title=(request.POST.get("title", "").strip() or "YouTube video")[:300],
                    source_name=request.POST.get("channel", "YouTube")[:200],
                    entry_type=EntryType.YOUTUBE,
                    youtube_video_id=video_id,
                    source_url=f"https://www.youtube.com/watch?v={video_id}",
                    source_published_at=initial.get("source_published_at"),
                    event_date=initial.get("event_date"),
                    is_favorite=True,
                )
            elif entry is not None and entry.is_favorite != favorite:
                entry.is_favorite = favorite
                entry.save(update_fields=["is_favorite", "updated_at"])
            if entry is not None and favorite:
                entry.add_country_tags(initial["countries"])
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
    return list_entries(request)


@never_cache
@require_http_methods(["GET"])
def list_entries(request):
    params = request.GET.copy()
    rewind = params.pop("rewind", [""])[-1] == "1"
    before = params.pop("rewind_before", [""])[-1]
    rewind_date = None
    if rewind:
        try:
            if before:
                end = date.fromisoformat(before)
                if end.isoformat() != before:
                    raise ValueError
            else:
                start, end = date_bounds(params)
                if start is None:
                    today = timezone.localdate()
                    end = today + timedelta(days=1) if today < date.max else None
        except ValueError:
            return JsonResponse({"error": "Enter a valid date."}, status=400)
        seek = filtered_entries(params, for_display=False, apply_date=False)
        if end is not None:
            seek = seek.filter(updated_at__lt=date_boundary(end))
        latest = seek.order_by("-updated_at").values_list("updated_at", flat=True).first()
        if latest is None:
            return JsonResponse({"date": None, "exhausted": True})
        rewind_date = timezone.localtime(latest).date()
        for key in ("year", "month", "day"):
            params.pop(key, None)
        params["date"] = rewind_date.isoformat()
    entries = filtered_entries(params)
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
    if rewind:
        context["total_entries"] = summary["total"]
        return JsonResponse({"date": rewind_date.isoformat(), "exhausted": False, "url": refresh_url,
                             "html": render_to_string("journal/partials/entry_results.html", context, request=request)})
    if is_paging or request.headers.get("X-Journal-Filtering") == "1":
        context["total_entries"] = summary["total"] or Entry.objects.exists()
        return render(request, "journal/partials/entry_results.html", context)
    collections = list(Collection.objects.annotate(entry_count=Count("entries")).order_by(Lower("name"), "name", "id"))
    selected = next((item for item in collections if str(item.pk) == request.GET.get("collection")), None)
    date_parts = {key: params.get(key, "") for key in ("year", "month", "day")}
    if params.get("date"):
        try:
            selected_date = date.fromisoformat(params["date"])
            date_parts = {key: str(getattr(selected_date, key)) for key in date_parts}
        except ValueError:
            pass
    sort = entry_sort(params)
    order = "asc" if request.GET.get("order") == "asc" else "desc"
    editor_data = {str(item.pk): {
        "id": str(item.pk), "name": item.name, "description": item.description,
        "delete_url": reverse("journal:collection_delete", args=[item.pk]),
    } for item in collections if not item.is_builtin}
    selected_data = editor_data.get(str(selected.pk)) if selected else None
    codes = list(dict.fromkeys(code.upper() for code in params.getlist("country") if len(code) == 2))
    country_names = dict(Country.objects.filter(pk__in=codes).values_list("pk", "name")) if codes else {}
    country_filters = [{"name": "country", "value": code, "label": country_names.get(code, code)} for code in codes]
    linked_filters = [{"name": name, "value": "1", "label": label} for name, label in (
        ("favorite", "Favorites"), ("pinned", "Pinned"), ("undated", "Without event date"), ("untagged", "Without country tags"),
    ) if params.get(name) == "1"]
    if params.get("collection") and not selected:
        linked_filters.append({"name": "collection", "value": params["collection"],
                               "label": "Unfiled" if params["collection"] == "unfiled" else "Missing collection"})
    extra_filters = [("country", code) for code in codes]
    extra_filters += [(key, value) for key in ("date", "favorite", "pinned", "undated", "untagged")
                      for value in params.getlist(key) if value and (key == "date" or value == "1")]
    context.update({
        "collections": collections, "selected_collection": selected,
        "collection_editor_data": editor_data, "collection_form": CollectionForm(),
        "collection_modal": "edit" if request.GET.get("edit_collection") and selected_data else "new" if request.GET.get("create_collection") else "",
        "sort": sort, "order": order, "date_parts": date_parts,
        "filter_mode": "exclude" if params.get("filter_mode") == "exclude" else "include",
        "selected_types": params.getlist("type"),
        "entry_types": EntryType.choices,
        "filters": request.GET,
        "country_filters": country_filters, "linked_filters": linked_filters,
        "extra_filters": extra_filters,
        "total_entries": Entry.objects.count(),
    })
    return page(request, "core/partials/journal.html", context)


def initial_entry(request, parameters=None):
    parameters = request.GET if parameters is None else parameters
    initial = {"entry_type": parameters.get("type") if parameters.get("type") in EntryType.values else EntryType.NOTE}
    for field, parameter in (("title", "title"), ("source_url", "url"), ("source_name", "source")):
        if value := parameters.get(parameter):
            limit = {"title": 300, "source_name": 200}.get(field)
            initial[field] = value[:limit] if limit else value
    if video := parameters.get("video"):
        try:
            video_id, seconds = parse_youtube_reference(video)
            initial.setdefault("source_url", f"https://www.youtube.com/watch?v={video_id}")
            if seconds is not None:
                initial["youtube_start_seconds"] = seconds
        except ValidationError:
            pass
    codes = {c.upper() for c in parameters.getlist("country")}
    if initial["entry_type"] in {EntryType.ARTICLE, EntryType.YOUTUBE}:
        from news.services.country_matcher import matched_country_codes
        codes.update(matched_country_codes(initial.get("title", "")))
    initial["countries"] = list(Country.objects.filter(code__in=codes).values_list("pk", flat=True))
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
                initial["event_date"] = timezone.localtime(moment).date() if timezone.is_aware(moment) else moment.date()
        except ValueError:
            pass
    return initial


@require_http_methods(["POST"])
def quick_save(request):
    if request.POST.get("type") not in {EntryType.ARTICLE, EntryType.YOUTUBE}:
        return JsonResponse({"message": "Choose an article or video to save."}, status=422)
    initial = initial_entry(request, request.POST)
    data = QueryDict(mutable=True)
    for field in ("title", "entry_type", "source_url", "source_name"):
        data[field] = initial.get(field, "")
    if moment := initial.get("source_published_at"):
        data["source_published_at"] = moment.isoformat()
    if seconds := initial.get("youtube_start_seconds"):
        data["youtube_start_seconds"] = seconds
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
            entry.add_country_tags(country.pk for country in form.cleaned_data["countries"])
    return JsonResponse({**bookmark_details(entry), "created": created})


@never_cache
@require_http_methods(["POST"])
def bookmark_status(request):
    videos, urls = request.POST.getlist("video"), request.POST.getlist("url")
    if len(videos) + len(urls) > 200 or any(not VIDEO_ID.fullmatch(value) for value in videos) or any(len(value) > 2048 for value in urls):
        return JsonResponse({"message": "Choose valid articles or videos."}, status=400)
    return JsonResponse({"bookmarks": bookmark_states(videos, urls)})


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


def entry_revision(entry):
    return entry.updated_at.isoformat() if entry and entry.updated_at else ""


def entry_images(contents):
    ids = set()
    for content in contents:
        if content.body_format == BodyFormat.RICHTEXT:
            ids.update(image_ids(validate_document(content.body)))
    return ids


def save_entry(form, sections, previous):
    # Call while holding the write transaction that checked the editor revision.
    before = entry_images([previous, *previous.sections.all()]) if previous else set()
    entry = form.save()
    sections.instance = entry
    section_objects = sections.save(commit=False)
    for section in sections.deleted_objects:
        section.delete()
    for section in section_objects:
        section.entry = entry
        section.save()
    contents = [entry, *entry.sections.all()]
    codes = {code for content in contents for code in referenced_countries(content.body, content.body_format)}
    entry.countries.add(*Country.objects.filter(code__in=codes))
    after = entry_images(contents)
    now = timezone.now()
    if before - after:
        entry.attachments.filter(pk__in=before - after, detached_at__isnull=True).update(detached_at=now)
    if after:
        entry.attachments.filter(pk__in=after, detached_at__isnull=False).update(detached_at=None)
    Attachment.objects.filter(detached_at__lte=now - IMAGE_UNDO_GRACE).delete()
    return entry


@require_http_methods(["POST"])
@write_transaction()
def autosave(request, pk):
    previous = Entry.objects.filter(pk=pk).first()
    attempt = request.POST.get("save_attempt", "")[:64]
    revision = entry_revision(previous)
    if previous and attempt:
        receipt = previous.editor_save_receipt
        if receipt.get("attempt") == attempt and receipt["result"]["revision"] == revision:
            return JsonResponse(receipt["result"])
    if request.POST.get("entry_revision") != revision or (previous is None and DeletedEntry.objects.filter(pk=pk).exists()):
        return JsonResponse({"message": ENTRY_CONFLICT}, status=409)
    entry = Entry.objects.get(pk=pk) if previous else Entry(pk=pk)
    data = request.POST.copy()
    if not data.get("title", "").strip():
        data["title"] = "Untitled"
    section_data, prefixes = section_submission(data, entry)
    for prefix in prefixes:
        if section_data.get(prefix + "-DELETE"):
            continue
        if not section_data.get(prefix + "-title", "").strip():
            if any(section_data.get(prefix + "-" + field, "").strip() for field in ("body", "source_url", "source_name", "source_published_at", "youtube_start_seconds")):
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
    entry = save_entry(form, sections, previous)
    section_ids = {prefixes.get(section.prefix, section.prefix): {"id": str(section.instance.pk), "title": section.instance.title} for section in sections.forms if not section.instance._state.adding and not section.cleaned_data.get("DELETE")}
    result = {
        "edit_url": reverse("journal:edit", args=[entry.pk]), "read_url": entry.get_absolute_url(),
        "title": entry.title, "sections": section_ids, "countries": list(entry.countries.values_list("pk", flat=True)),
        "revision": entry_revision(entry),
    }
    if attempt:
        Entry.objects.filter(pk=entry.pk).update(editor_save_receipt={"attempt": attempt, "result": result})
    return JsonResponse(result)


@require_http_methods(["GET", "POST"])
def edit(request, pk=None):
    if pk:
        entry = get_object_or_404(Entry, pk=pk)
    elif request.method == "POST":
        # The first ordinary submission uses the same identity as autosave.
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
    revision = request.POST.get("entry_revision", "" if entry._state.adding else None) if request.method == "POST" else entry_revision(entry)
    if request.method == "POST" and not adding_section:
        with write_transaction():
            previous = Entry.objects.filter(pk=entry.pk).first()
            form_valid, sections_valid = form.is_valid(), sections.is_valid()
            if form_valid and sections_valid:
                if revision != entry_revision(previous) or (previous is None and (pk or DeletedEntry.objects.filter(pk=entry.pk).exists())):
                    form.add_error(None, ENTRY_CONFLICT)
                else:
                    entry = save_entry(form, sections, previous)
                    messages.success(request, "Saved.")
                    return navigate(request, reverse("journal:edit", args=[entry.pk]))
    initial_published = form.initial.get("source_published_at") if entry._state.adding else None
    return page(request, "journal/edit.html", {
        "entry": entry, "form": form, "section_formset": sections, "is_new": entry._state.adding,
        "entry_revision": revision, "journal_country_aliases": country_aliases(),
        "initial_source_published_at": request.POST.get("initial_source_published_at", "") if form.is_bound else initial_published.isoformat() if initial_published else "",
    })


@require_http_methods(["GET"])
def detail(request, pk):
    entry = get_object_or_404(Entry.objects.select_related("collection").prefetch_related("countries", "sections__attachments", "attachments__section"), pk=pk)
    return page(request, "journal/detail.html", {"entry": entry, "main_attachments": [image for image in entry.attachments.all() if not image.section_id]})


@require_http_methods(["GET", "POST"])
def delete_entry(request, pk):
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    json_request = request.headers.get("Accept") == "application/json"
    if request.method == "POST" and form.is_valid():
        video, url = request.POST.get("video", ""), request.POST.get("url", "")
        if json_request and (bool(video) == bool(url) or (video and not VIDEO_ID.fullmatch(video)) or len(url) > 2048):
            return JsonResponse({"message": "Choose the article or video to remove from Journal."}, status=422)
        with write_transaction():
            entry = Entry.objects.filter(pk=pk).first()
            if json_request and (entry is None or (video and video != entry.youtube_video_id) or (url and url != entry.source_url)):
                return JsonResponse({
                    "message": "The saved item changed. The card has been updated.",
                    "bookmarks": bookmark_states([video] if video else (), [url] if url else ()),
                }, status=409)
            if entry is None:
                raise Http404
            videos = [entry.youtube_video_id] if entry.youtube_video_id else []
            urls = [entry.source_url] if entry.source_url else []
            DeletedEntry.objects.get_or_create(pk=entry.pk)
            entry.delete()
            if json_request:
                return JsonResponse({"deleted": True, "bookmarks": bookmark_states(videos, urls)})
        messages.success(request, "Entry deleted, including its sections and local images.")
        return navigate(request, reverse("core:journal"))
    if request.method == "POST" and json_request:
        return JsonResponse({"message": "Confirm removal from Journal."}, status=422)
    entry = get_object_or_404(Entry, pk=pk)
    return page(request, "journal/confirm_delete.html", {"form": form, "title": f"Delete {entry.title}?", "description": "This deletes the entry, its subsections and its local images.", "cancel_url": entry.get_absolute_url()})


@require_http_methods(["GET", "POST"])
def collection_edit(request, pk=None):
    identity = pk
    if not identity and request.method == "POST":
        identity = request.POST.get("collection_id")
    if identity:
        try:
            identity = Collection._meta.pk.to_python(identity)
        except ValidationError:
            return HttpResponse("Choose an existing collection.", status=400)
    collection = get_object_or_404(Collection.objects.exclude(name__in=BUILTIN_COLLECTION_NAMES), pk=identity) if identity else Collection()
    if request.method == "GET":
        url = reverse("journal:list")
        return navigate(request, url + (f"?collection={collection.pk}&edit_collection=1" if pk else "?create_collection=1"))
    form = CollectionForm(request.POST if request.method == "POST" else None, instance=collection)
    if form.is_valid():
        with write_transaction():
            collection = form.save()
        messages.success(request, "Collection saved.")
        params = QueryDict(request.POST.get("return_query", ""), mutable=True)
        for key in list(params):
            if key not in {"q", "collection", "type", "filter_mode", "sort", "order", "year", "month", "day", "country", "date", "favorite", "pinned", "undated", "untagged"}:
                params.pop(key)
        params["collection"] = str(collection.pk)
        return navigate(request, reverse("journal:list") + "?" + params.urlencode())
    response = render(request, "journal/partials/collection_form.html", {
        "collection_form": form, "collection": collection, "collection_id": str(collection.pk) if identity else "",
        "return_query": request.POST.get("return_query", ""),
    })
    response.headers["HX-Trigger"] = json.dumps({"world-journal:server-notices": {"notices": [
        {"kind": "warning", "message": "Check the collection details."},
    ]}})
    return response


@require_http_methods(["GET", "POST"])
def collection_delete(request, pk):
    collection = get_object_or_404(Collection.objects.exclude(name__in=BUILTIN_COLLECTION_NAMES), pk=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with write_transaction():
            for types in ((EntryType.YOUTUBE,), (EntryType.ARTICLE, EntryType.BOOKMARK), (EntryType.NOTE,)):
                target = default_collection(types[0])
                Entry.objects.filter(collection=collection, entry_type__in=types).update(collection=target, updated_at=timezone.now())
            collection.delete()
        messages.success(request, "Collection deleted.")
        return navigate(request, reverse("journal:list"))
    return navigate(request, reverse("journal:list") + f"?collection={collection.pk}&edit_collection=1")


@require_http_methods(["POST"])
def upload_attachment(request, pk):
    entry = get_object_or_404(Entry, pk=pk)
    form = AttachmentForm(request.POST, request.FILES, entry=entry)
    if form.is_valid():
        from .documents import image_url
        image = form.save(commit=False)
        try:
            with write_transaction():
                if not Entry.objects.filter(pk=entry.pk).exists() or (image.section_id and not entry.sections.filter(pk=image.section_id).exists()):
                    return JsonResponse({"message": ENTRY_CONFLICT}, status=409)
                if request.POST.get("inline") == "1":
                    image.detached_at = timezone.now()
                image.save()
        except (DatabaseError, OSError):
            if image.file and image.file._committed:
                try:
                    image.file.storage.delete(image.file.name)
                except OSError:
                    logging.getLogger(__name__).warning("A rolled-back image upload could not be removed from local media.")
            return JsonResponse({"message": "The image could not be saved. Check available space and try again."}, status=503)
        return JsonResponse({"id": str(image.pk), "src": image_url(image.pk), "alt": image.original_name, "width": image.width, "height": image.height})
    return JsonResponse({"message": str(next(iter(form.errors.values()))[0])}, status=422)


@require_http_methods(["GET"])
def image(request, attachment_pk):
    attachment = get_object_or_404(Attachment, pk=attachment_pk)
    try:
        response = FileResponse(attachment.file.open("rb"), content_type=attachment.content_type)
    except OSError as error:
        raise Http404("This image is unavailable.") from error
    response["Cache-Control"] = "private, max-age=3600"
    response["X-Content-Type-Options"] = "nosniff"
    return response


@require_http_methods(["GET", "POST"])
def delete_attachment(request, pk, attachment_pk):
    attachment = get_object_or_404(Attachment.objects.select_related("entry"), pk=attachment_pk, entry_id=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    url = attachment.entry.get_absolute_url()
    if request.method == "POST" and form.is_valid():
        with write_transaction():
            entry = get_object_or_404(Entry, pk=pk)
            if attachment.pk in entry_images([entry, *entry.sections.all()]):
                messages.warning(request, "Remove this image in the editor and save the entry.")
                return navigate(request, url)
            attachment.delete()
            Entry.objects.filter(pk=pk).update(updated_at=timezone.now())
        messages.success(request, "Image deleted.")
        return navigate(request, url)
    return page(request, "journal/confirm_delete.html", {"form": form, "title": "Delete this image?", "description": "The uploaded image will be removed from local storage.", "cancel_url": url})
