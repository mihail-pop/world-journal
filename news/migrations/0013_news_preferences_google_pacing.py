from django.db import migrations, models

from news.google_pacing import validate_pacing


class Migration(migrations.Migration):
    dependencies = [("news", "0012_persist_refresh_cycle")]

    operations = [
        migrations.AddField(
            model_name="newspreferences", name="google_pacing",
            field=models.JSONField(blank=True, default=dict, validators=[validate_pacing]),
        ),
    ]
