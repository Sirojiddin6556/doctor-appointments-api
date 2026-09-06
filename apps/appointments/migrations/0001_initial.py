# Сгенерировано Django 5.2.17 05.09.2026 в 12:42.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Appointment",
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
                (
                    "start_time",
                    models.DateTimeField(
                        help_text="Copied from slot.start_time at booking time."
                    ),
                ),
                (
                    "end_time",
                    models.DateTimeField(
                        help_text="Copied from slot.end_time at booking time."
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("booked", "Booked"),
                            ("cancelled", "Cancelled"),
                            ("completed", "Completed"),
                        ],
                        db_index=True,
                        default="booked",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("cancelled_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
