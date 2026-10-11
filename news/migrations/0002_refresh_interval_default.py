import django.core.validators
from django.db import migrations, models


def update_legacy_preferences(apps, schema_editor):
    preferences = apps.get_model("news", "NewsPreferences")
    preferences.objects.filter(freshness_minutes=15).update(freshness_minutes=30)
    choices = apps.get_model("news", "SourcePreference")
    choices.objects.filter(source_id__in=(
        "al_arabiya_en", "al_arabiya_en_top", "al_arabiya_en_news",
        "al_arabiya_en_business", "al_arabiya_en_energy", "al_arabiya_en_life",
    )).delete()


class Migration(migrations.Migration):
    dependencies = [("news", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="newspreferences",
            name="freshness_minutes",
            field=models.PositiveSmallIntegerField(
                default=30,
                validators=[django.core.validators.MinValueValidator(5), django.core.validators.MaxValueValidator(120)],
            ),
        ),
        migrations.RunPython(update_legacy_preferences, migrations.RunPython.noop),
    ]
