# Сгенерировано Django 5.2.17 05.09.2026 в 12:42.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Doctor",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("specialization", models.CharField(db_index=True, max_length=100)),
                ("branch", models.CharField(db_index=True, max_length=100)),
            ],
            options={
                "ordering": ["id"],
            },
        ),
    ]
