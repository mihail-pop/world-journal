import re

from django import forms
from django.forms import BaseFormSet, formset_factory

from journal.models import Entry

from .models import Country, CountryProfile, MapPreset, TerritoryDetails


class PresetColorField(forms.CharField):
    palette = (
        ("Blue", "#4a90e2"), ("Teal", "#52abb8"), ("Green", "#4aab83"),
        ("Gold", "#d5ac47"), ("Apricot", "#da9567"), ("Coral", "#dd6858"),
        ("Rose", "#cf78a3"), ("Lilac", "#a57bd5"), ("Slate", "#8295af"),
        ("Sand", "#b4a087"),
    )

    def __init__(self, **kwargs):
        super().__init__(max_length=40, widget=forms.TextInput(attrs={
            "data-preset-color-value": "", "placeholder": "RGB or hex",
            "spellcheck": "false", "autocomplete": "off",
        }), **kwargs)

    def to_python(self, value):
        value = super().to_python(value).strip().lower()
        if not value:
            return value
        if re.fullmatch(r"#[0-9a-f]{6}", value):
            return value
        if re.fullmatch(r"#[0-9a-f]{3}", value):
            return "#" + "".join(char * 2 for char in value[1:])
        rgb = re.fullmatch(r"(?:rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)|(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3}))", value)
        if rgb:
            channels = [int(channel) for channel in rgb.groups() if channel is not None]
            if all(channel <= 255 for channel in channels):
                return "#" + "".join(f"{channel:02x}" for channel in channels)
        raise forms.ValidationError("Use a hex color or RGB values from 0 to 255.")


class PresetForm(forms.ModelForm):
    default_color = PresetColorField(required=False, label="Ungrouped countries")

    class Meta:
        model = MapPreset
        fields = ("name", "description", "default_color")
        widgets = {
            "name": forms.TextInput(attrs={"placeholder": "Preset name", "aria-label": "Preset name"}),
            "description": forms.Textarea(attrs={"rows": 2, "placeholder": "Description", "aria-label": "Description"}),
        }


class ColorGroupForm(forms.Form):
    title = forms.CharField(max_length=160, required=False, widget=forms.TextInput(attrs={"placeholder": "Group title", "aria-label": "Group title"}))
    color = PresetColorField(initial="#4a90e2")
    countries = forms.ModelMultipleChoiceField(queryset=Country.objects.all(), required=False, widget=forms.SelectMultiple(attrs={"data-country-select": "", "data-select-summary": "Add countries"}))


class ColorGroupFormSet(BaseFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)
        form.fields["DELETE"].widget.attrs.update({"data-native-checkbox": "", "class": "visually-hidden"})

    def clean(self):
        if any(self.errors):
            return
        assigned = set()
        for form in self.forms:
            data = form.cleaned_data
            if data.get("DELETE"):
                continue
            for country in data.get("countries", []):
                if country.pk in assigned:
                    raise forms.ValidationError(f"{country.name} is selected in more than one color group. Remove it from one group first.")
                assigned.add(country.pk)
        if any(len(group["title"]) > 160 for group in self.groups()):
            raise forms.ValidationError("Groups using the same color are combined. Shorten their combined titles to 160 characters or choose different colors.")

    def assignments(self):
        return {country.pk: form.cleaned_data["color"] for form in self.forms if not form.cleaned_data.get("DELETE") for country in form.cleaned_data.get("countries", [])}

    def groups(self):
        grouped = {}
        for form in self.forms:
            data = form.cleaned_data
            if data.get("DELETE") or not data.get("color"):
                continue
            group = grouped.setdefault(data["color"], {"color": data["color"], "titles": [], "countries": []})
            title = data.get("title", "").strip()
            if title and title not in group["titles"]:
                group["titles"].append(title)
            group["countries"].extend(country.pk for country in data.get("countries", []))
        return [{"color": group["color"], "title": " / ".join(group["titles"]), "countries": group["countries"]} for group in grouped.values()]


ColorGroups = formset_factory(ColorGroupForm, formset=ColorGroupFormSet, extra=1, can_delete=True, max_num=252, validate_max=True, absolute_max=252)


class TerritoryDetailsForm(forms.ModelForm):
    class Meta:
        model = TerritoryDetails
        fields = ("name", "population", "area", "capital", "languages", "currency", "government", "notes")
        labels = {"area": "Surface area (km²)", "languages": "Languages", "capital": "Capital / administrative center"}


class DuplicatePresetForm(forms.ModelForm):
    class Meta:
        model = MapPreset
        fields = ("name",)


class CountryProfileForm(forms.ModelForm):
    class Meta:
        model = CountryProfile
        fields = ("entry",)
        labels = {"entry": "Overview Journal entry"}

    def __init__(self, *args, country, **kwargs):
        super().__init__(*args, **kwargs)
        entries = Entry.objects.filter(countries=country, country_profile__isnull=True)
        if self.instance.entry_id:
            entries = Entry.objects.filter(pk=self.instance.entry_id) | entries
        self.fields["entry"].queryset = entries.only("id", "title").order_by("title", "id").distinct()
        self.fields["entry"].empty_label = "No overview note"
        self.fields["entry"].widget = forms.RadioSelect()
        self.fields["entry"].widget.choices = self.fields["entry"].choices
