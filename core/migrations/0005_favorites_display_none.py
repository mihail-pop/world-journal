from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0004_map_menu_open")]

    operations = [
        migrations.AlterField(
            model_name="appsettings", name="map_favorites_display",
            field=models.CharField(
                choices=[("hearts", "Map hearts"), ("list", "Favorites list"), ("none", "Hidden")],
                default="hearts", max_length=8,
            ),
        ),
    ]
