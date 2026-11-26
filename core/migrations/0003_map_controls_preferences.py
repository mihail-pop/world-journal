from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0002_persist_preferences")]

    operations = [
        migrations.AddField(model_name="appsettings", name="map_favorites_display",
            field=models.CharField(choices=[("hearts", "Map hearts"), ("list", "Favorites list")], default="hearts", max_length=8)),
        migrations.AddField(model_name="appsettings", name="map_menu_position",
            field=models.JSONField(blank=True, default=None, null=True)),
    ]
