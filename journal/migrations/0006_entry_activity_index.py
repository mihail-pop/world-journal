from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("journal", "0005_alphabetical_collections")]

    operations = [
        migrations.AddIndex(
            model_name="entry", index=models.Index(fields=["-updated_at", "id"], name="journal_activity_idx"),
        ),
    ]
