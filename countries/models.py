import uuid

from django.core.validators import RegexValidator
from django.db import models


class Country(models.Model):
    """Stable journal identity; map geometry and metadata remain in bundled JSON."""

    code = models.CharField(primary_key=True, max_length=2)
    name = models.CharField(max_length=160)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name


validate_map_color = RegexValidator(r"\A#[0-9A-Fa-f]{6}\Z", "Use a six-digit color such as #4a90e2.")


class CountryFavorite(models.Model):
    country = models.OneToOneField(Country, primary_key=True, on_delete=models.CASCADE, related_name="favorite")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("country__name",)


class MapPreset(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=160, unique=True)
    description = models.TextField(blank=True)
    default_color = models.CharField(max_length=7, blank=True, validators=[validate_map_color])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name", "id")

    def __str__(self):
        return self.name


class PresetCountry(models.Model):
    preset = models.ForeignKey(MapPreset, on_delete=models.CASCADE, related_name="country_colors")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="preset_colors")
    color = models.CharField(max_length=7, validators=[validate_map_color])

    class Meta:
        ordering = ("country__name",)
        constraints = [models.UniqueConstraint(fields=("preset", "country"), name="unique_preset_country")]


class PresetColorGroup(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    preset = models.ForeignKey(MapPreset, on_delete=models.CASCADE, related_name="color_groups")
    color = models.CharField(max_length=7, validators=[validate_map_color])
    title = models.CharField(max_length=160, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [models.UniqueConstraint(fields=("preset", "color"), name="unique_preset_group_color")]


class MapPersonalState(models.Model):
    # One shared active preset; zero or one row exists, always at key 1.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    active_preset = models.ForeignKey(MapPreset, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="map_personal_state_singleton")]


class CountryProfile(models.Model):
    country = models.OneToOneField(Country, primary_key=True, on_delete=models.CASCADE, related_name="profile")
    entry = models.OneToOneField("journal.Entry", null=True, blank=True, on_delete=models.SET_NULL, related_name="country_profile")
    updated_at = models.DateTimeField(auto_now=True)
