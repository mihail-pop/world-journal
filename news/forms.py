from django import forms
from django.db import transaction

from .models import NewsPreferences, SourcePreference


class NewsPreferencesForm(forms.Form):
    freshness_minutes = forms.IntegerField(
        label="Background refresh interval (minutes)", min_value=5, max_value=120,
        help_text="Refresh enabled feeds automatically while the Django server runs. Cached articles and videos remain available during refreshes.",
    )

    def __init__(self, *args, registry, choices, freshness, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["freshness_minutes"].initial = max(5, min(120, freshness // 60))
        self.items = (*registry.sources, *registry.providers, *registry.feeds)
        for item in self.items:
            self.fields[f"enabled_{item.id}"] = forms.BooleanField(
                label=getattr(item, "display_name", getattr(item, "section_label", item.id)),
                required=False, disabled=not item.enabled_by_default,
                initial=item.enabled_by_default and choices.get(item.id, True),
                widget=forms.CheckboxInput(attrs={"form": "news-preferences"}),
            )

    def save(self):
        with transaction.atomic():
            NewsPreferences.objects.update_or_create(pk=1, defaults={"freshness_minutes": self.cleaned_data["freshness_minutes"]})
            for item in self.items:
                if item.enabled_by_default:
                    SourcePreference.objects.update_or_create(
                        source_id=item.id, defaults={"enabled": self.cleaned_data[f"enabled_{item.id}"]},
                    )
