from django.db import migrations, models


def move_mixed_to_notes(apps, schema_editor):
    for name in ("Entry", "EntrySection"):
        apps.get_model("journal", name).objects.filter(entry_type="mixed").update(entry_type="note")


class Migration(migrations.Migration):
    dependencies = [("journal", "0001_initial")]
    operations = [
        migrations.RunPython(move_mixed_to_notes, migrations.RunPython.noop),
        *[migrations.AlterField(model_name=name, name="entry_type", field=models.CharField(choices=[("note", "Note"), ("article", "Article"), ("bookmark", "Bookmark"), ("youtube", "YouTube video")], default="note", max_length=16)) for name in ("entry", "entrysection")],
    ]
