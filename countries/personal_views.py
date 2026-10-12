import json

from django.db import transaction
from django.http import JsonResponse, QueryDict
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.views import render_page
from journal.formatting import render_body
from journal.forms import default_collection
from journal.models import Entry
from journal.views import ConfirmationForm, navigate

from .forms import ColorGroups, CountryProfileForm, DuplicatePresetForm, PresetForm
from .models import Country, CountryFavorite, CountryProfile, MapPersonalState, MapPreset, PresetColorGroup, PresetCountry


def personal_snapshot():
    state = MapPersonalState.objects.select_related("active_preset").filter(pk=1).first()
    active = state.active_preset if state else None
    return {
        "favorites": list(CountryFavorite.objects.values_list("country_id", flat=True)),
        "presets": [{"id": str(p.pk), "name": p.name} for p in MapPreset.objects.all()],
        "active_preset": str(active.pk) if active else None,
        "active_preset_name": active.name if active else "",
        "groups": preset_groups(active) if active else [],
        "default_color": active.default_color if active else "",
        "colors": dict(active.country_colors.values_list("country_id", "color")) if active else {},
    }


@never_cache
@require_http_methods(["GET"])
def personal_data(request):
    return JsonResponse(personal_snapshot())


@require_http_methods(["POST"])
def favorite(request, iso2):
    country = get_object_or_404(Country, pk=iso2.upper())
    value = request.POST.get("favorite")
    if value not in {"1", "0"}:
        return JsonResponse({"error": "Choose whether to favorite this country."}, status=400)
    if value == "1":
        CountryFavorite.objects.get_or_create(country=country)
    else:
        CountryFavorite.objects.filter(country=country).delete()
    if request.headers.get("Accept") == "application/json":
        return JsonResponse({"country": country.pk, "favorite": value == "1"})
    if request.POST.get("origin") == "countries":
        return navigate(request, reverse("countries:index") + f"?country={country.pk}")
    return navigate(request, reverse("core:map") + f"?country={country.pk}")


def page(request, template, context):
    return render_page(request, "settings", page_template=template, context=context)


@require_http_methods(["GET"])
def preset_list(request):
    state = MapPersonalState.objects.filter(pk=1).first()
    presets = MapPreset.objects.prefetch_related("country_colors__country", "color_groups")
    for preset in presets:
        preset.display_groups = preset_groups(preset)
        names = {row.country_id: row.country.name for row in preset.country_colors.all()}
        for group in preset.display_groups:
            group["country_names"] = [names[code] for code in group["countries"]]
    return page(request, "countries/preset_list.html", {"presets": presets, "active_preset_id": state.active_preset_id if state else None})


def preset_groups(preset):
    grouped = {}
    if not preset._state.adding:
        for row in preset.country_colors.all():
            grouped.setdefault(row.color.lower(), []).append(row.country_id)
        result = [{"color": group.color.lower(), "title": group.title, "countries": grouped.pop(group.color.lower(), [])} for group in preset.color_groups.all()]
    else:
        result = []
    # Old version 1 backups have colors but no group metadata.
    return result + [{"color": color, "title": "", "countries": codes} for color, codes in grouped.items()]


def save_preset(form, groups):
    preset = form.save()
    preset.country_colors.all().delete()
    PresetCountry.objects.bulk_create([PresetCountry(preset=preset, country_id=code, color=color) for code, color in groups.assignments().items()])
    preset.color_groups.all().delete()
    PresetColorGroup.objects.bulk_create([PresetColorGroup(preset=preset, color=group["color"], title=group["title"], position=index) for index, group in enumerate(groups.groups())])
    return preset


@require_http_methods(["GET", "POST"])
def preset_edit(request, pk=None):
    preset = get_object_or_404(MapPreset, pk=pk) if pk else MapPreset()
    form = PresetForm(request.POST if request.method == "POST" else None, instance=preset)
    rows = request.POST.copy() if request.method == "POST" else None
    adding = request.method == "POST" and request.POST.get("action") == "add_group"
    if adding:
        try:
            rows["colors-TOTAL_FORMS"] = str(min(238, max(0, int(rows.get("colors-TOTAL_FORMS", "0"))) + 1))
        except ValueError:
            pass
    colors = ColorGroups(rows, initial=preset_groups(preset), prefix="colors")
    if request.method == "POST" and not adding:
        valid, colors_valid = form.is_valid(), colors.is_valid()
        if valid and colors_valid:
            with transaction.atomic():
                preset = save_preset(form, colors)
            url = reverse("core:map") + f"?edit_preset={preset.pk}" if request.POST.get("action") == "edit_map" else reverse("countries:preset_list")
            return navigate(request, url)
    return page(request, "countries/preset_edit.html", {"form": form, "color_formset": colors, "preset": preset, "is_new": pk is None})


@never_cache
@require_http_methods(["GET", "POST"])
def preset_data(request, pk=None):
    preset = get_object_or_404(MapPreset, pk=pk) if pk else MapPreset()
    if request.method == "POST":
        try:
            payload = json.loads(request.body)
            if not isinstance(payload, dict) or not isinstance(payload.get("groups"), list) or len(payload["groups"]) > 238:
                raise ValueError
            if not all(isinstance(payload.get(key, ""), str) for key in ("name", "description", "default_color", "updated_at")):
                raise ValueError
            rows = QueryDict(mutable=True)
            rows.update({"name": payload.get("name", ""), "description": payload.get("description", ""), "default_color": payload.get("default_color", ""), "colors-TOTAL_FORMS": str(len(payload["groups"])), "colors-INITIAL_FORMS": "0"})
            for index, group in enumerate(payload["groups"]):
                if not isinstance(group, dict) or not isinstance(group.get("countries"), list):
                    raise ValueError
                if not isinstance(group.get("color", ""), str) or not isinstance(group.get("title", ""), str) or len(group["countries"]) > 238 or not all(isinstance(code, str) for code in group["countries"]):
                    raise ValueError
                rows[f"colors-{index}-color"] = group.get("color", "")
                rows[f"colors-{index}-title"] = group.get("title", "")
                rows.setlist(f"colors-{index}-countries", group["countries"])
        except (ValueError, TypeError):
            return JsonResponse({"error": "The color groups could not be read. Reload the editor and try again."}, status=400)
        form = PresetForm(rows, instance=preset)
        groups = ColorGroups(rows, prefix="colors")
        valid, groups_valid = form.is_valid(), groups.is_valid()
        if not valid or not groups_valid:
            errors = [str(error) for values in form.errors.values() for error in values]
            errors.extend(str(error) for error in groups.non_form_errors())
            errors.extend(str(error) for fields in groups.errors for values in fields.values() for error in values)
            return JsonResponse({"error": " ".join(errors)}, status=400)
        with transaction.atomic():
            # A second editor must not overwrite a newer saved version silently.
            current_stamp = MapPreset.objects.filter(pk=pk).values_list("updated_at", flat=True).first() if pk else None
            if pk and (not current_stamp or current_stamp.isoformat() != payload.get("updated_at")):
                return JsonResponse({"error": "This preset changed since you opened it. Your draft is kept; reopen the preset to load the saved version."}, status=409)
            preset = save_preset(form, groups)
            MapPersonalState.objects.update_or_create(pk=1, defaults={"active_preset": preset})
    return JsonResponse({"id": str(preset.pk) if not preset._state.adding else "new", "name": preset.name, "description": preset.description, "default_color": preset.default_color, "updated_at": preset.updated_at.isoformat() if preset.updated_at else "", "groups": preset_groups(preset)})


@require_http_methods(["POST"])
def preset_activate(request, pk=None):
    preset = get_object_or_404(MapPreset, pk=pk) if pk else None
    MapPersonalState.objects.update_or_create(pk=1, defaults={"active_preset": preset})
    if request.headers.get("Accept") == "application/json":
        return JsonResponse(personal_snapshot())
    return navigate(request, reverse("countries:preset_list"))


@require_http_methods(["GET", "POST"])
def preset_duplicate(request, pk):
    original = get_object_or_404(MapPreset, pk=pk)
    form = DuplicatePresetForm(request.POST if request.method == "POST" else None, initial={"name": f"{original.name[:150]} copy"})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            copy = form.save(commit=False)
            copy.description, copy.default_color = original.description, original.default_color
            copy.save()
            PresetCountry.objects.bulk_create([PresetCountry(preset=copy, country_id=row.country_id, color=row.color) for row in original.country_colors.all()])
            PresetColorGroup.objects.bulk_create([PresetColorGroup(preset=copy, color=group["color"], title=group["title"], position=index) for index, group in enumerate(preset_groups(original))])
        return navigate(request, reverse("countries:preset_edit", kwargs={"pk": copy.pk}))
    return page(request, "countries/preset_duplicate.html", {"form": form, "preset": original})


@require_http_methods(["GET", "POST"])
def preset_delete(request, pk):
    preset = get_object_or_404(MapPreset, pk=pk)
    form = ConfirmationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        preset.delete()
        return navigate(request, reverse("countries:preset_list"))
    return page(request, "countries/confirm_delete.html", {"form": form, "title": f"Delete preset {preset.name}?", "description": "Only this preset and its color assignments are deleted. Favorites and Journal entries are kept.", "cancel_url": reverse("countries:preset_list")})


@never_cache
@require_http_methods(["GET"])
def country_notes(request, iso2):
    country = get_object_or_404(Country, pk=iso2.upper())
    return render(request, "countries/partials/notes.html", country_notes_context(country))


def country_notes_context(country):
    profile = CountryProfile.objects.select_related("entry").filter(country=country).first()
    entry = profile.entry if profile else None
    images = list(entry.attachments.filter(section__isnull=True)[:3]) if entry else []
    return {
        "country": country, "overview": entry, "overview_images": images,
        "overview_preview": render_body(entry.body[:1600], entry.body_format) if entry else "",
        "overview_truncated": bool(entry and len(entry.body) > 1600),
        "recent_entries": Entry.objects.filter(countries=country).only("id", "title", "entry_type", "created_at")[:6],
    }


@require_http_methods(["GET", "POST"])
def profile_edit(request, iso2):
    country = get_object_or_404(Country, pk=iso2.upper())
    profile = CountryProfile.objects.filter(country=country).first() or CountryProfile(country=country)
    form = CountryProfileForm(request.POST if request.method == "POST" else None, instance=profile, country=country)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            profile = form.save()
            if profile.entry_id:
                profile.entry.countries.add(country)
        return navigate(request, reverse("core:map") + f"?country={country.pk}&section=notes")
    return render_page(request, "journal", page_template="countries/profile_edit.html", context={"form": form, "country": country})


@require_http_methods(["POST"])
def profile_create(request, iso2):
    country = get_object_or_404(Country, pk=iso2.upper())
    with transaction.atomic():
        profile, _created = CountryProfile.objects.get_or_create(country=country)
        if not profile.entry_id:
            entry = Entry.objects.create(title=f"{country.name}: overview", collection=default_collection("note"))
            entry.countries.add(country)
            profile.entry = entry
            profile.save(update_fields=["entry", "updated_at"])
        entry_id = profile.entry_id
    return navigate(request, reverse("journal:edit", kwargs={"pk": entry_id}))
