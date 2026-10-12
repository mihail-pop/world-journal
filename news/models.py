import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class ArchivedNews(models.Model):
    """Bounded feed history, independent of permanent Journal bookmarks."""

    identity = models.CharField(primary_key=True, max_length=64)
    fingerprint = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=8, choices=(("articles", "Article"), ("videos", "Video")))
    title = models.CharField(max_length=300)
    link = models.URLField(max_length=2048)
    publisher = models.CharField(max_length=200)
    summary = models.CharField(max_length=2000, blank=True)
    video_id = models.CharField(max_length=11, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now)
    sort_date = models.DateTimeField()
    expires_at = models.DateTimeField(db_index=True)
    metadata_bytes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("-sort_date", "identity")
        indexes = [
            models.Index(fields=["kind", "-sort_date", "identity"], name="news_archive_order_idx"),
            models.Index(fields=["sort_date", "identity"], name="news_archive_trim_idx"),
        ]


class ArchivedNewsSource(models.Model):
    item = models.ForeignKey(ArchivedNews, on_delete=models.CASCADE, related_name="origins")
    feed_id = models.CharField(max_length=96, db_index=True)
    source_id = models.CharField(max_length=80)
    category = models.CharField(max_length=8)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "feed_id"], name="news_archive_unique_feed")]


class ArchivedNewsCountry(models.Model):
    item = models.ForeignKey(ArchivedNews, on_delete=models.CASCADE, related_name="country_tags")
    country_code = models.CharField(max_length=2, db_index=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "country_code"], name="news_archive_unique_country")]


class SourcePreference(models.Model):
    """Shared choices for registry IDs; endpoint configuration stays in the registry."""

    source_id = models.CharField(max_length=80, primary_key=True)
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["source_id"]


class NewsPreferences(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    freshness_minutes = models.PositiveSmallIntegerField(
        default=720, validators=[MinValueValidator(360), MaxValueValidator(720)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="news_preferences_singleton"),
            models.CheckConstraint(condition=models.Q(freshness_minutes__gte=360, freshness_minutes__lte=720), name="news_freshness_bounds"),
        ]


class CustomSource(models.Model):
    class Kind(models.TextChoices):
        RSS = "rss", "Article RSS / Atom"
        YOUTUBE = "youtube", "YouTube channel"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="extra_feeds")
    name = models.CharField(max_length=160, blank=True)
    url = models.URLField(max_length=2048, unique=True)
    feed_format = models.CharField(max_length=40, blank=True)
    channel_id = models.CharField(max_length=24, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["parent_id", "created_at", "id"]

    @property
    def registry_id(self):
        return f"custom_{self.id.hex}"

    def clean(self):
        from django.core.exceptions import ValidationError
        from .services.custom_sources import normalize_location
        from .services.fetch import FeedFetchError
        from .registry import YOUTUBE_CHANNEL_PATTERN

        if self.parent_id:
            parent = self._state.fields_cache.get("parent")
            if self.parent_id == self.id or self.kind != self.Kind.RSS or parent and (parent.kind != self.Kind.RSS or parent.parent_id):
                raise ValidationError({"parent": "Additional article feeds must belong directly to an article publisher."})

        try:
            normalize_location(self.url, self.kind)
        except FeedFetchError as error:
            raise ValidationError({"url": str(error)}) from error
        if self.verified_at and self.kind == self.Kind.YOUTUBE:
            if not YOUTUBE_CHANNEL_PATTERN.fullmatch(self.channel_id):
                raise ValidationError({"channel_id": "A verified source requires a valid channel ID."})
            if self.url != f"https://www.youtube.com/feeds/videos.xml?channel_id={self.channel_id}":
                raise ValidationError({"url": "The verified feed URL must match its channel ID."})
