from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from journal.models import Entry

from .models import CountryProfile, MapPreset, PresetCountry


class PresetForm(forms.ModelForm):
    class Meta:
        model = MapPreset
        fields = ("name", "description", "default_color")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "default_color": forms.TextInput(attrs={"placeholder": "#4a90e2"})}
        help_texts = {"default_color": "Optional: color for countries without their own row. Leave empty to keep the ordinary map color."}

    def clean_default_color(self):
        return self.cleaned_data["default_color"].lower()


class PresetCountryForm(forms.ModelForm):
    class Meta:
        model = PresetCountry
        fields = ("country", "color")
        widgets = {"color": forms.TextInput(attrs={"type": "color"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["country"].widget.attrs["data-country-select"] = ""
        if not self.instance.pk:
            self.initial["color"] = "#4a90e2"

    def clean_color(self):
        return self.cleaned_data["color"].lower()


class PresetColorFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        codes = set()
        for form in self.forms:
            data = form.cleaned_data
            if data.get("DELETE") or not data.get("country"):
                continue
            code = data["country"].pk
            if code in codes:
                raise forms.ValidationError("Choose each country only once in a preset.")
            codes.add(code)


PresetFormSet = inlineformset_factory(MapPreset, PresetCountry, form=PresetCountryForm, formset=PresetColorFormSet, extra=1, can_delete=True, max_num=238, validate_max=True)


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
        self.fields["entry"].help_text = "Choose an entry tagged with this country. Clearing the selection keeps the Journal entry."
