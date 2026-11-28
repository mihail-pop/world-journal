import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("countries", "0007_consolidate_app_settings")]

    operations = [
        migrations.CreateModel(
            name="CountrySelection",
            fields=[
                ("country", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True,
                    related_name="selection_count", serialize=False, to="countries.country")),
                ("count", models.PositiveBigIntegerField(default=0)),
            ],
        ),
    ]
