from django.db import migrations


def prepare_collections(apps, schema_editor):
    Collection = apps.get_model("journal", "Collection")
    Entry = apps.get_model("journal", "Entry")
    alias = schema_editor.connection.alias
    collections = {name: Collection.objects.using(alias).get_or_create(name=name)[0] for name in ("Articles", "Notes", "Videos")}
    for name, kinds in (("Articles", ("article", "bookmark")), ("Videos", ("youtube",))):
        Entry.objects.using(alias).filter(collection__isnull=True, entry_type__in=kinds).update(collection=collections[name])
    Entry.objects.using(alias).filter(collection__isnull=True).update(collection=collections["Notes"])


class Migration(migrations.Migration):
    dependencies = [("journal", "0002_remove_mixed_research")]
    operations = [migrations.RunPython(prepare_collections, migrations.RunPython.noop)]
