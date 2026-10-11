from pathlib import Path

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory

from .models import Attachment, Collection, Entry, EntrySection, EntryType
from .validators import MAX_TIMESTAMP, parse_youtube_reference


CONTENT_FIELDS = ("title", "entry_type", "body", "source_url", "source_name", "source_published_at", "youtube_start_seconds")


class ContentForm(forms.ModelForm):
    youtube_reference = forms.CharField(required=False, label="YouTube URL or video ID", help_text="Watch, Shorts, youtu.be links, or the 11-character ID.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs["placeholder"] = "Untitled entry"
        self.fields["body"].widget.attrs.update(rows=12, placeholder="Start writing…", **{"data-journal-body": ""})
        self.fields["source_published_at"].widget = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")
        self.fields["source_published_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"]
        self.fields["youtube_start_seconds"].label = "Start time in seconds"
        self.fields["youtube_start_seconds"].max_value = MAX_TIMESTAMP
        self.fields["source_url"].label = "Source URL"
        self.fields["source_published_at"].label = "Source publication time (UTC)"
        if self.instance.youtube_video_id:
            self.initial["youtube_reference"] = self.instance.youtube_video_id

    def clean(self):
        cleaned = super().clean()
        # Keep the legacy database/export field, but every editor uses Markdown.
        self.instance.body_format = "markdown"
        reference = cleaned.get("youtube_reference", "").strip()
        video_id = ""
        if reference:
            try:
                video_id, seconds = parse_youtube_reference(reference)
                if cleaned.get("youtube_start_seconds") is None and seconds is not None:
                    cleaned["youtube_start_seconds"] = seconds
            except ValidationError as error:
                self.add_error("youtube_reference", error)
        elif cleaned.get("source_url"):
            # A source may also be a video, regardless of its organizational
            # tag. Ordinary article/playlist URLs remain ordinary sources.
            try:
                video_id, seconds = parse_youtube_reference(cleaned["source_url"])
                if cleaned.get("youtube_start_seconds") is None and seconds is not None:
                    cleaned["youtube_start_seconds"] = seconds
            except ValidationError:
                pass
        self.instance.youtube_video_id = video_id
        if video_id and not cleaned.get("source_url"):
            cleaned["source_url"] = f"https://www.youtube.com/watch?v={video_id}"
        return cleaned


class EntryForm(ContentForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["collection"].empty_label = "Automatic collection"
        self.fields["collection"].help_text = "Articles, Videos or Notes, unless you choose another collection."

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


SectionFormSet = inlineformset_factory(Entry, EntrySection, form=SectionForm, extra=0, can_delete=True, max_num=200, validate_max=True)


class CollectionForm(forms.ModelForm):
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
