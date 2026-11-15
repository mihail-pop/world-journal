from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import BaseInlineFormSet, inlineformset_factory
from django.utils import timezone

from .models import Attachment, BodyFormat, BUILTIN_COLLECTION_NAMES, Collection, Entry, EntrySection, EntryType
from .documents import image_ids, serialize_document, validate_document
from .validators import MAX_TIMESTAMP, parse_youtube_reference


CONTENT_FIELDS = ("title", "entry_type", "body", "source_url", "source_name", "source_published_at", "youtube_start_seconds")


class ContentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs["placeholder"] = "Title"
        self.fields["entry_type"].label = "Type"
        self.fields["entry_type"].required = False
        self.fields["body"].widget.attrs.update(hidden=True, **{"data-journal-body": ""})
        self.editor_html = ""
        if not self.is_bound and self.instance.body and self.instance.body_format != BodyFormat.RICHTEXT:
            from .formatting import render_body
            self.editor_html = str(render_body(self.instance.body, self.instance.body_format))
        self.fields["source_published_at"].widget = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
        self.fields["source_published_at"].input_formats = ["%Y-%m-%d"]
        self.fields["youtube_start_seconds"].label = "Start time in seconds"
        self.fields["youtube_start_seconds"].max_value = MAX_TIMESTAMP
        self.fields["source_url"].label = "Source URL"
        self.fields["source_published_at"].label = "Release date"
        self.fields["source_url"].widget.attrs["placeholder"] = "https://"
        if self.instance.youtube_video_id and not self.instance.source_url:
            self.initial["source_url"] = self.instance.watch_url

    def clean_entry_type(self):
        return self.cleaned_data.get("entry_type") or EntryType.NOTE

    def clean_body(self):
        value = self.cleaned_data.get("body", "")
        if not value:
            return ""
        document = validate_document(value)
        ids = image_ids(document)
        if ids:
            owner_id = self.instance.entry_id if isinstance(self.instance, EntrySection) else self.instance.pk
            existing = set(Attachment.objects.filter(entry_id=owner_id, pk__in=ids).values_list("pk", flat=True))
            if ids != existing:
                raise ValidationError("An image does not belong to this document or has been deleted.")
        return serialize_document(document)

    def clean(self):
        cleaned = super().clean()
        self.instance.body_format = BodyFormat.RICHTEXT
        video_id = ""
        if cleaned.get("source_url"):
            # A source may also be a video, regardless of its organizational
            # tag. Ordinary article/playlist URLs remain ordinary sources.
            try:
                video_id, seconds = parse_youtube_reference(cleaned["source_url"])
                if cleaned.get("youtube_start_seconds") is None and seconds is not None:
                    cleaned["youtube_start_seconds"] = seconds
            except ValidationError as error:
                if cleaned.get("entry_type") == EntryType.YOUTUBE:
                    self.add_error("source_url", error)
        self.instance.youtube_video_id = video_id
        return cleaned


class EntryForm(ContentForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collection"].empty_label = "Automatic collection"
        for name in ("is_favorite", "is_pinned"):
            self.fields[name].widget.attrs["hidden"] = True

    def clean(self):
        cleaned = super().clean()
        # A publication is a useful starting point, not an event-date rule:
        # existing entries can keep a different date or deliberately clear it.
        if self.instance._state.adding and not cleaned.get("event_date") and (published := cleaned.get("source_published_at")):
            cleaned["event_date"] = timezone.localtime(published).date() if timezone.is_aware(published) else published.date()
        return cleaned

    class Meta:
        model = Entry
        fields = (*CONTENT_FIELDS, "collection", "event_date", "countries", "is_favorite", "is_pinned")
        widgets = {
            "event_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "countries": forms.SelectMultiple(attrs={"size": 8, "data-country-select": ""}),
        }

    def save(self, commit=True):
        entry = super().save(commit=False)
        if not entry.collection_id:
            entry.collection = default_collection(entry.entry_type)
        if commit:
            entry.save()
            self.save_m2m()
        return entry


def default_collection(entry_type):
    name = "Videos" if entry_type == EntryType.YOUTUBE else "Articles" if entry_type in {EntryType.ARTICLE, EntryType.BOOKMARK} else "Notes"
    collection, _created = Collection.objects.get_or_create(name=name)
    return collection


class SectionForm(ContentForm):
    class Meta:
        model = EntrySection
        fields = (*CONTENT_FIELDS, "position")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["body"].widget.attrs["rows"] = 7
        self.fields["position"].widget = forms.HiddenInput()


class SectionInlineFormSet(BaseInlineFormSet):
    def add_fields(self, form, index):
        # The editor allocates a stable UUID before its first autosave. Django's
        # inline formset otherwise clears a new parent's default primary key.
        entry_id = self.instance.pk
        super().add_fields(form, index)
        self.instance.pk = entry_id


SectionFormSet = inlineformset_factory(Entry, EntrySection, form=SectionForm, formset=SectionInlineFormSet, extra=0, can_delete=True, max_num=200, validate_max=True)


class CollectionForm(forms.ModelForm):
    def clean_name(self):
        name = self.cleaned_data["name"]
        if self.instance.pk and self.instance.is_builtin:
            raise ValidationError("This collection has a fixed name.")
        if name.casefold() in {value.casefold() for value in BUILTIN_COLLECTION_NAMES}:
            raise ValidationError("Choose a different name. This name belongs to a built-in collection.")
        return name

    class Meta:
        model = Collection
        fields = ("name", "description", "position")
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class AttachmentForm(forms.ModelForm):
    file = forms.ImageField(label="Image", help_text="JPEG, PNG, WebP or GIF, up to 10 MB.")

    class Meta:
        model = Attachment
        fields = ("file", "caption", "section")

    def __init__(self, *args, entry, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.entry = entry
        self.fields["section"].queryset = entry.sections.all()
        self.fields["section"].empty_label = "Main entry"
        self.fields["file"].widget.attrs["accept"] = "image/jpeg,image/png,image/webp,image/gif"

    def clean_file(self):
        upload = self.cleaned_data["file"]
        limit = settings.JOURNAL_IMAGE_MAX_BYTES
        if upload.size > limit:
            raise ValidationError(f"Images must be no larger than {limit // (1024 * 1024)} MB.")
        image = upload.image
        formats = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"), "WEBP": (".webp", "image/webp"), "GIF": (".gif", "image/gif")}
        if image.format not in formats:
            raise ValidationError("Use a JPEG, PNG, WebP or GIF image.")
        if image.width * image.height > 40_000_000:
            raise ValidationError("This image is too large. Resize it below 40 megapixels.")
        extension, content_type = formats[image.format]
        self.instance.original_name = Path(upload.name).name[:255]
        self.instance.content_type = content_type
        self.instance.byte_size = upload.size
        self.instance.width = image.width
        self.instance.height = image.height
        upload.name = f"image{extension}"
        return upload
