from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("news", "0003_customsource")]
    operations = [
        migrations.AddField(
            model_name="customsource", name="parent",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name="extra_feeds", to="news.customsource"),
        ),
        migrations.AlterModelOptions(name="customsource", options={"ordering": ["parent_id", "created_at", "id"]}),
    ]
