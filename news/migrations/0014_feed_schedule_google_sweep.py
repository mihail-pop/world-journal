from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("news", "0013_news_preferences_google_pacing"), ("countries", "0008_countryselection")]

    operations = [
        migrations.AddField(
            model_name="feedschedule", name="google_sweep_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="feedschedule", name="google_sweep_order",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
