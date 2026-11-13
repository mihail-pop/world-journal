from django.db import models


class AppSettings(models.Model):
    class Theme(models.TextChoices):
        DARK = "dark", "Dark"
        BROWN = "brown", "Brown"
        CHARCOAL = "charcoal", "Charcoal"
        LIGHT = "light", "Light"
        PINK = "pink", "Pink"
        CAKE = "cake", "Cake"
        GREEN = "green", "Green"
        TEAL = "teal", "Teal"
        PLUM = "plum", "Plum"

    class Font(models.TextChoices):
        INTER = "inter", "Inter"
        OS = "os", "OS (Native)"
        OVERPASS = "overpass", "Overpass"
        ROBOTO = "roboto", "Roboto"
        SEGOE = "segoe", "Segoe"

    class MapType(models.TextChoices):
        TERRAIN = "terrain", "Terrain"
        PLAIN = "plain", "Simple"
        ADVENTURE = "adventure", "Adventure"

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    theme = models.CharField(max_length=8, choices=Theme.choices, default=Theme.DARK)
    font = models.CharField(max_length=16, choices=Font.choices, default=Font.INTER)
    map_type = models.CharField(max_length=12, choices=MapType.choices, default=MapType.TERRAIN)
    home_country = models.ForeignKey("countries.Country", null=True, blank=True, on_delete=models.SET_NULL, related_name="home_settings")
    active_preset = models.ForeignKey("countries.MapPreset", null=True, blank=True, on_delete=models.SET_NULL, related_name="active_settings")
    country_names = models.BooleanField(default=True)
    capital_names = models.BooleanField(default=False)
    city_names = models.BooleanField(default=True)
    region_names = models.BooleanField(default=False)
    small_country_markers = models.BooleanField(default=False)
    protected_areas = models.BooleanField(default=False)
    vegetation = models.BooleanField(default=True)
    relief = models.BooleanField(default=True)
    water = models.BooleanField(default=True)
    transport = models.BooleanField(default=True)
    buildings = models.BooleanField(default=False)
    land_use = models.BooleanField(default=False)
    administrative_borders = models.BooleanField(default=True)
    points_of_interest = models.BooleanField(default=False)
    all_other_text = models.BooleanField(default=True)
    revision = models.PositiveBigIntegerField(default=0, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="app_settings_singleton")]
