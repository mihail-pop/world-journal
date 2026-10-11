from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.views import render_page
from journal.formatting import render_body
from journal.models import Entry
from journal.views import ConfirmationForm, navigate

from .forms import CountryProfileForm, DuplicatePresetForm, PresetForm, PresetFormSet
from .models import Country, CountryFavorite, CountryProfile, MapPersonalState, MapPreset, PresetCountry


def personal_snapshot():
    state = MapPersonalState.objects.select_related("active_preset").filter(pk=1).first()
    active = state.active_preset if state else None
    return {
        "favorites": list(CountryFavorite.objects.values_list("country_id", flat=True)),
        "presets": [{"id": str(p.pk), "name": p.name} for p in MapPreset.objects.all()],
        "active_preset": str(active.pk) if active else None,
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
    return navigate(request, reverse("core:map") + f"?country={country.pk}")


def page(request, template, context):
    return render_page(request, "settings", page_template=template, context=context)


@require_http_methods(["GET"])
def preset_list(request):
    state = MapPersonalState.objects.filter(pk=1).first()
    return page(request, "countries/preset_list.html", {"presets": MapPreset.objects.prefetch_related("country_colors__country"), "active_preset_id": state.active_preset_id if state else None})


@require_http_methods(["GET", "POST"])
def preset_edit(request, pk=None):
    preset = get_object_or_404(MapPreset, pk=pk) if pk else MapPreset()
    form = PresetForm(request.POST if request.method == "POST" else None, instance=preset)
    rows = request.POST.copy() if request.method == "POST" else None
    adding = request.method == "POST" and request.POST.get("action") == "add_country"
    if adding:
        try:
            rows["colors-TOTAL_FORMS"] = str(min(238, max(0, int(rows.get("colors-TOTAL_FORMS", "0"))) + 1))
        except ValueError:
            pass
    colors = PresetFormSet(rows, instance=preset, prefix="colors")
    if request.method == "POST" and not adding:
        valid, colors_valid = form.is_valid(), colors.is_valid()
        if valid and colors_valid:
            with transaction.atomic():
                preset = form.save()
                colors.instance = preset
                colors.save()
            return navigate(request, reverse("countries:preset_list"))
    return page(request, "countries/preset_edit.html", {"form": form, "color_formset": colors, "preset": preset, "is_new": pk is None})


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
    profile = CountryProfile.objects.select_related("entry").filter(country=country).first()
    entry = profile.entry if profile else None
    images = list(entry.attachments.filter(section__isnull=True)[:3]) if entry else []
    return render(request, "countries/partials/notes.html", {
        "country": country, "overview": entry, "overview_images": images,
        "overview_preview": render_body(entry.body[:1600], entry.body_format) if entry else "",
        "overview_truncated": bool(entry and len(entry.body) > 1600),
        "recent_entries": Entry.objects.filter(countries=country).only("id", "title", "entry_type", "created_at")[:6],
    })


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
            entry = Entry.objects.create(title=f"{country.name}: overview")
            entry.countries.add(country)
            profile.entry = entry
            profile.save(update_fields=["entry", "updated_at"])
        entry_id = profile.entry_id
    return navigate(request, reverse("journal:edit", kwargs={"pk": entry_id}))
