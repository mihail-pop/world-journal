from django import forms

from core.database import write_transaction

from .models import CustomSource, NewsPreferences, SourcePreference


def single_feed_providers(registry):
    feeds = {}
    for feed in registry.feeds:
        feeds.setdefault(feed.provider_id, []).append(feed.id)
    return {provider_id: identities[0] for provider_id, identities in feeds.items() if len(identities) == 1}


class NewsPreferencesForm(forms.Form):
    freshness_minutes = forms.TypedChoiceField(
        label="Background refresh interval", coerce=int,
        choices=[(360, "Every 6 hours"), (480, "Every 8 hours"), (600, "Every 10 hours"), (720, "Every 12 hours")],
        help_text="Refresh enabled feeds automatically while the Django server runs. Cached articles and videos remain available during refreshes.",
    )

    def __init__(self, *args, registry, choices, freshness, **kwargs):
        super().__init__(*args, **kwargs)
        minutes = freshness // 60
        self.fields["freshness_minutes"].initial = minutes if minutes in (360, 480, 600, 720) else 720
        self.items = (*registry.sources, *registry.providers, *registry.feeds)
        for item in self.items:
            self.fields[f"enabled_{item.id}"] = forms.BooleanField(
                label=getattr(item, "display_name", getattr(item, "section_label", item.id)),
                required=False, disabled=not item.enabled_by_default,
                initial=item.enabled_by_default and choices.get(item.id, True),
                widget=forms.CheckboxInput(attrs={"form": "news-preferences", "data-source-choice": item.id}),
            )
        self.single_feed_providers = single_feed_providers(registry)
        for provider_id, feed_id in self.single_feed_providers.items():
            provider_field = self.fields[f"enabled_{provider_id}"]
            feed_field = self.fields[f"enabled_{feed_id}"]
            provider_field.initial = provider_field.initial and feed_field.initial
            provider_field.disabled = provider_field.disabled or feed_field.disabled

    def save(self):
        feed_providers = {feed_id: provider_id for provider_id, feed_id in self.single_feed_providers.items()}
        with write_transaction():
            NewsPreferences.objects.update_or_create(pk=1, defaults={"freshness_minutes": self.cleaned_data["freshness_minutes"]})
            for item in self.items:
                if item.enabled_by_default:
                    SourcePreference.objects.update_or_create(
                        source_id=item.id, defaults={"enabled": self.cleaned_data[f"enabled_{feed_providers.get(item.id, item.id)}"]},
                    )


class CustomSourceForm(forms.Form):
    kind = forms.ChoiceField(label="Source type", choices=[(CustomSource.Kind.RSS, "News articles"), (CustomSource.Kind.YOUTUBE, "YouTube channel")])
    location = forms.CharField(label="Link", max_length=2048,
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


class AdditionalFeedForm(CustomSourceForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].initial = CustomSource.Kind.RSS
        self.fields["kind"].disabled = True
        self.fields["kind"].widget = forms.HiddenInput()
        self.fields["name"].label = "Feed label (optional)"
