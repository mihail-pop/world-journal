from django.db import migrations
from django.db.models.functions import Lower


class Migration(migrations.Migration):
    dependencies = [("journal", "0004_rich_text_documents")]

    operations = [
        migrations.AlterModelOptions(
            name="collection", options={"ordering": (Lower("name"), "name", "id")},
        ),
        migrations.RemoveField(model_name="collection", name="position"),
    ]
