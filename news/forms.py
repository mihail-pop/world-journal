from django import forms
from django.db import transaction

from .models import CustomSource, NewsPreferences, SourcePreference


class NewsPreferencesForm(forms.Form):
    freshness_minutes = forms.IntegerField(
        label="Background refresh interval (minutes)", min_value=5, max_value=120,
        help_text="Refresh enabled feeds automatically while the Django server runs. Cached articles and videos remain available during refreshes.",
    )

    def __init__(self, *args, registry, choices, freshness, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["freshness_minutes"].initial = max(5, min(120, freshness // 60))
        # A custom RSS source has one feed; its publisher switch is its sole choice.
        self.items = (*registry.sources, *registry.providers, *(feed for feed in registry.feeds if not feed.id.startswith("custom_")))
        for item in self.items:
            self.fields[f"enabled_{item.id}"] = forms.BooleanField(
                label=getattr(item, "display_name", getattr(item, "section_label", item.id)),
                required=False, disabled=not item.enabled_by_default,
                initial=item.enabled_by_default and choices.get(item.id, True),
                widget=forms.CheckboxInput(attrs={"form": "news-preferences", "data-source-choice": item.id}),
            )

    def save(self):
        with transaction.atomic():
            NewsPreferences.objects.update_or_create(pk=1, defaults={"freshness_minutes": self.cleaned_data["freshness_minutes"]})
            for item in self.items:
                if item.enabled_by_default:
                    SourcePreference.objects.update_or_create(
                        source_id=item.id, defaults={"enabled": self.cleaned_data[f"enabled_{item.id}"]},
                    )


class CustomSourceForm(forms.Form):
    kind = forms.ChoiceField(label="Source type", choices=CustomSource.Kind.choices)
    location = forms.CharField(label="Feed or channel", max_length=2048,
                              widget=forms.TextInput(attrs={"placeholder": "https://…", "autocomplete": "off"}))
    name = forms.CharField(label="Name (optional)", max_length=160, required=False)

    def clean(self):
        data = super().clean()
        if data.get("location") and data.get("kind"):
            from .services.custom_sources import normalize_location
            from .services.fetch import FeedFetchError

            try:
                data["location"] = normalize_location(data["location"], data["kind"])
            except FeedFetchError as error:
                self.add_error("location", str(error))
            else:
                if CustomSource.objects.filter(url=data["location"]).exists():
                    self.add_error("location", "This source has already been added.")
        return data
