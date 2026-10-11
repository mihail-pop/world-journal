from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


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
        default=30, validators=[MinValueValidator(5), MaxValueValidator(120)],
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name="news_preferences_singleton"),
            models.CheckConstraint(condition=models.Q(freshness_minutes__gte=5, freshness_minutes__lte=120), name="news_freshness_bounds"),
        ]
