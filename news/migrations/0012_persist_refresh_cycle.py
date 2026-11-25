from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("news", "0011_archive_source_lookup")]

    operations = [
        migrations.AddField(
            model_name="feedschedule", name="cycle_finished_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="feedschedule", name="cycle_manual",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="feedschedule", name="manual_requested",
            field=models.BooleanField(default=False),
        ),
    ]
