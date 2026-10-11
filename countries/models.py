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
