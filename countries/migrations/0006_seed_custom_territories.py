from django.db import migrations


TERRITORIES = (
    ("XD", "Dhekelia Sovereign Base Area"), ("XL", "Somaliland"), ("XK", "Kosovo"),
    ("XG", "Guantanamo Bay Naval Base"), ("XC", "Northern Cyprus"),
    ("XU", "United Nations Buffer Zone in Cyprus"), ("XI", "Siachen Glacier"),
    ("XA", "Akrotiri Sovereign Base Area"), ("XP", "Southern Patagonian Ice Field (disputed section)"),
    ("XB", "Bir Tawil"), ("XV", "Spratly Islands"), ("XN", "Bajo Nuevo Bank"),
    ("XE", "Serranilla Bank"), ("XR", "Scarborough Shoal"),
)


def seed(apps, schema_editor):
    Country = apps.get_model("countries", "Country")
    for code, name in TERRITORIES:
        Country.objects.get_or_create(code=code, defaults={"name": name, "is_custom": True})
        Country.objects.filter(pk=code).update(is_custom=True)


class Migration(migrations.Migration):
    dependencies = [("countries", "0005_territorydetails_country_is_custom")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
