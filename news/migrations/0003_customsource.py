import uuid
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("news", "0002_refresh_interval_default")]

    operations = [migrations.CreateModel(
        name="CustomSource",
        fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("kind", models.CharField(choices=[("rss", "Article RSS / Atom"), ("youtube", "YouTube channel")], max_length=12)),
            ("name", models.CharField(blank=True, max_length=160)),
            ("url", models.URLField(max_length=2048, unique=True)),
            ("feed_format", models.CharField(blank=True, max_length=40)),
            ("channel_id", models.CharField(blank=True, max_length=24)),
            ("verified_at", models.DateTimeField(blank=True, null=True)),
            ("last_checked_at", models.DateTimeField(blank=True, null=True)),
            ("last_error", models.CharField(blank=True, max_length=240)),
            ("created_at", models.DateTimeField(auto_now_add=True)),
            ("updated_at", models.DateTimeField(auto_now=True)),
        ],
        options={"ordering": ["created_at", "id"]},
    )]
