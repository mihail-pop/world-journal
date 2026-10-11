import django.core.validators
from django.db import migrations, models


def upgrade_intervals(apps, schema_editor):
    preferences = apps.get_model("news", "NewsPreferences")
    preferences.objects.using(schema_editor.connection.alias).filter(freshness_minutes__lt=360).update(freshness_minutes=720)


def restore_intervals(apps, schema_editor):
    preferences = apps.get_model("news", "NewsPreferences")
    preferences.objects.using(schema_editor.connection.alias).filter(freshness_minutes__gt=120).update(freshness_minutes=30)


class Migration(migrations.Migration):
    dependencies = [("news", "0004_customsource_parent")]
    operations = [
        migrations.RemoveConstraint(model_name="newspreferences", name="news_freshness_bounds"),
        migrations.RunPython(upgrade_intervals, restore_intervals),
        migrations.AlterField(
            model_name="newspreferences", name="freshness_minutes",
            field=models.PositiveSmallIntegerField(default=720, validators=[
                django.core.validators.MinValueValidator(360), django.core.validators.MaxValueValidator(720),
            ]),
        ),
        migrations.AddConstraint(
            model_name="newspreferences",
            constraint=models.CheckConstraint(condition=models.Q(freshness_minutes__gte=360, freshness_minutes__lte=720), name="news_freshness_bounds"),
        ),
    ]
