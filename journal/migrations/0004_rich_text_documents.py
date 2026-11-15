from django.db import migrations, models
from django.db.models import F


def populate_search_text(apps, schema_editor):
    for name in ("Entry", "EntrySection"):
        apps.get_model("journal", name).objects.update(body_text=F("body"))


class Migration(migrations.Migration):
    dependencies = [("journal", "0003_builtin_collections")]
    operations = [
        migrations.AddField(model_name="entry", name="body_text", field=models.TextField(blank=True, editable=False)),
        migrations.AddField(model_name="entrysection", name="body_text", field=models.TextField(blank=True, editable=False)),
        migrations.AlterField(model_name="entry", name="body_format", field=models.CharField(choices=[("richtext", "Rich text"), ("markdown", "Markdown"), ("plain", "Plain text")], default="richtext", max_length=16)),
        migrations.AlterField(model_name="entrysection", name="body_format", field=models.CharField(choices=[("richtext", "Rich text"), ("markdown", "Markdown"), ("plain", "Plain text")], default="richtext", max_length=16)),
        migrations.RunPython(populate_search_text, migrations.RunPython.noop),
    ]
