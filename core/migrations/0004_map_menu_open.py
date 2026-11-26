from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0003_map_controls_preferences")]

    operations = [
        migrations.AddField(
            model_name="appsettings", name="map_menu_open",
            field=models.BooleanField(default=False),
        ),
    ]
