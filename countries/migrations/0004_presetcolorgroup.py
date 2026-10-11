import uuid

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


def seed_groups(apps, schema_editor):
    PresetCountry = apps.get_model("countries", "PresetCountry")
    PresetColorGroup = apps.get_model("countries", "PresetColorGroup")
    seen = set()
    positions = {}
    groups = []
    database = schema_editor.connection.alias
    for preset_id, color in PresetCountry.objects.using(database).order_by("preset_id", "country__name").values_list("preset_id", "color").iterator():
        color = color.lower()
        key = (preset_id, color)
        if key in seen:
            continue
        seen.add(key)
        position = positions.get(preset_id, 0)
        groups.append(PresetColorGroup(preset_id=preset_id, color=color, title="", position=position))
        positions[preset_id] = position + 1
    PresetColorGroup.objects.using(database).bulk_create(groups)


class Migration(migrations.Migration):
    dependencies = [("countries", "0003_countryfavorite_mappreset_countryprofile_and_more")]

    operations = [
        migrations.CreateModel(
            name="PresetColorGroup",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("color", models.CharField(max_length=7, validators=[django.core.validators.RegexValidator(r"\A#[0-9A-Fa-f]{6}\Z", "Use a six-digit color such as #4a90e2.")])),
                ("title", models.CharField(blank=True, max_length=160)),
                ("position", models.PositiveIntegerField(default=0)),
                ("preset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="color_groups", to="countries.mappreset")),
            ],
            options={
                "ordering": ("position", "id"),
                "constraints": [models.UniqueConstraint(fields=("preset", "color"), name="unique_preset_group_color")],
            },
        ),
        migrations.RunPython(seed_groups, migrations.RunPython.noop),
    ]
