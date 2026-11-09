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

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    theme = models.CharField(max_length=8, choices=Theme.choices, default=Theme.DARK)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="app_settings_singleton")]
