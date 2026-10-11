import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator
from django.db import models
from django.urls import reverse

from .validators import MAX_TIMESTAMP, validate_source_url, validate_video_id


class EntryType(models.TextChoices):
    NOTE = "note", "Note"
    ARTICLE = "article", "Article"
    BOOKMARK = "bookmark", "Bookmark"
    YOUTUBE = "youtube", "YouTube video"
    MIXED = "mixed", "Mixed research"


class BodyFormat(models.TextChoices):
    MARKDOWN = "markdown", "Markdown"
    PLAIN = "plain", "Plain text"


class Collection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "name", "id")

    def __str__(self):
        return self.name


class ResearchContent(models.Model):
    """Main entries and ordered subsections can each carry text and a reference."""

    title = models.CharField(max_length=300)
    body = models.TextField(blank=True)
    body_format = models.CharField(max_length=16, choices=BodyFormat.choices, default=BodyFormat.MARKDOWN)
    entry_type = models.CharField(max_length=16, choices=EntryType.choices, default=EntryType.NOTE)
    source_url = models.URLField(max_length=2048, blank=True, validators=[validate_source_url])
    source_name = models.CharField(max_length=200, blank=True)
    source_published_at = models.DateTimeField(null=True, blank=True)
    youtube_video_id = models.CharField(max_length=11, blank=True, validators=[validate_video_id])
    youtube_start_seconds = models.PositiveIntegerField(null=True, blank=True, validators=[MaxValueValidator(MAX_TIMESTAMP)])

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        errors = {}
        if self.entry_type in {EntryType.ARTICLE, EntryType.BOOKMARK} and not self.source_url:
            errors["source_url"] = "Add the article or bookmark URL."
        if self.entry_type == EntryType.YOUTUBE and not self.youtube_video_id:
            errors["__all__"] = "Add a YouTube video URL or ID."
        if self.youtube_start_seconds is not None and not self.youtube_video_id:
            errors["youtube_start_seconds"] = "A start time requires a YouTube video."
        if errors:
            raise ValidationError(errors)

    @property
    def watch_url(self):
        if not self.youtube_video_id:
            return ""
        url = f"https://www.youtube.com/watch?v={self.youtube_video_id}"
        if self.youtube_start_seconds:
            url += f"&t={self.youtube_start_seconds}s"
        return url

    @property
    def video_timestamp(self):
        seconds = self.youtube_start_seconds or 0
        hours, rest = divmod(seconds, 3600)
        minutes, seconds = divmod(rest, 60)
        return f"{hours}:{minutes:02}:{seconds:02}" if hours else f"{minutes}:{seconds:02}"


class Entry(ResearchContent):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection = models.ForeignKey(Collection, null=True, blank=True, on_delete=models.SET_NULL, related_name="entries")
    countries = models.ManyToManyField("countries.Country", blank=True, related_name="journal_entries")
    event_date = models.DateField(null=True, blank=True)
    is_favorite = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_pinned", "-created_at", "-id")
        indexes = [
            models.Index(fields=["event_date", "id"], name="journal_event_idx"),
            models.Index(fields=["-created_at", "id"], name="journal_created_idx"),
            models.Index(fields=["collection", "-created_at"], name="journal_collection_idx"),
            models.Index(fields=["entry_type", "event_date"], name="journal_type_date_idx"),
        ]
        constraints = [models.CheckConstraint(
            condition=models.Q(youtube_start_seconds__isnull=True) | ~models.Q(youtube_video_id=""),
            name="journal_entry_timestamp_video",
        )]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("journal:detail", kwargs={"pk": self.pk})


class EntrySection(ResearchContent):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="sections")
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("position", "created_at", "id")
        indexes = [models.Index(fields=["entry", "position"], name="journal_section_order_idx")]
        constraints = [models.CheckConstraint(
            condition=models.Q(youtube_start_seconds__isnull=True) | ~models.Q(youtube_video_id=""),
            name="journal_section_timestamp_video",
        )]

    def __str__(self):
        return self.title


def attachment_path(instance, filename):
    extension = Path(filename).suffix.lower()
    if extension not in {".jpg", ".png", ".webp", ".gif"}:
        extension = ".bin"
    return f"journal/{instance.entry_id}/{uuid.uuid4().hex}{extension}"


class Attachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="attachments")
    section = models.ForeignKey(EntrySection, null=True, blank=True, on_delete=models.SET_NULL, related_name="attachments")
    file = models.FileField(upload_to=attachment_path, max_length=300)
    original_name = models.CharField(max_length=255)
    caption = models.CharField(max_length=500, blank=True)
    content_type = models.CharField(max_length=100)
    byte_size = models.PositiveBigIntegerField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    position = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "created_at", "id")

    def clean(self):
        super().clean()
        if self.section_id and self.section.entry_id != self.entry_id:
            raise ValidationError({"section": "The image section must belong to this entry."})
