from django import forms
from django.forms import BaseFormSet, formset_factory

from journal.models import Entry

from .models import Country, CountryProfile, MapPreset, validate_map_color


class PresetForm(forms.ModelForm):
    class Meta:
        model = MapPreset
        fields = ("name", "description", "default_color")
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "default_color": forms.TextInput(attrs={"placeholder": "#4a90e2"})}
        help_texts = {"default_color": "Optional: color for countries outside your color groups. Leave empty to keep the ordinary map color."}

    def clean_default_color(self):
        return self.cleaned_data["default_color"].lower()


class ColorGroupForm(forms.Form):
    color = forms.CharField(max_length=7, validators=[validate_map_color], widget=forms.TextInput(attrs={"type": "color"}), initial="#4a90e2")
    countries = forms.ModelMultipleChoiceField(queryset=Country.objects.all(), required=False, widget=forms.SelectMultiple(attrs={"data-country-select": ""}))

    def clean_color(self):
        return self.cleaned_data["color"].lower()


class ColorGroupFormSet(BaseFormSet):
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

    def assignments(self):
        return {country.pk: form.cleaned_data["color"] for form in self.forms if not form.cleaned_data.get("DELETE") for country in form.cleaned_data.get("countries", [])}


ColorGroups = formset_factory(ColorGroupForm, formset=ColorGroupFormSet, extra=1, can_delete=True, max_num=238, validate_max=True, absolute_max=238)


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
