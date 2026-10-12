import uuid

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models, transaction


class Country(models.Model):
    """Stable ISO or explicitly local territory identity; geometry stays bundled."""

    code = models.CharField(primary_key=True, max_length=2)
    name = models.CharField(max_length=160)
    is_custom = models.BooleanField(default=False)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "countries"

    def __str__(self):
        return self.name


class TerritoryDetails(models.Model):
    country = models.OneToOneField(Country, primary_key=True, on_delete=models.CASCADE, related_name="territory_details")
    name = models.CharField(max_length=160)
    population = models.BigIntegerField(null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(9_223_372_036_854_775_807)])
    area = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    capital = models.CharField(max_length=160, blank=True)
    languages = models.CharField(max_length=300, blank=True)
    currency = models.CharField(max_length=160, blank=True)
    government = models.CharField(max_length=300, blank=True)
    notes = models.TextField(max_length=4000, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if not Country.objects.filter(pk=self.country_id, is_custom=True).exists():
            raise ValidationError("Local territory details can only belong to a custom territory.")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            Country.objects.filter(pk=self.country_id, is_custom=True).update(name=self.name)
        from journal.formatting import country_aliases
        transaction.on_commit(country_aliases.cache_clear)


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
