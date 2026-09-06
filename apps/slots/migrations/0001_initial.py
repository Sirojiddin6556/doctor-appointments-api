# Сгенерировано Django 5.2.17 05.09.2026 в 12:42.

import django.contrib.postgres.constraints
import django.db.models.deletion
from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("doctors", "0001_initial"),
    ]

    operations = [
        # Требуется для ExclusionConstraint (индекс GIST по врачу и tsrange),
        # который ниже обеспечивает правило 7 на уровне базы данных.
        BtreeGistExtension(),
        migrations.CreateModel(
            name="Slot",
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
                ("start_time", models.DateTimeField()),
                ("end_time", models.DateTimeField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "doctor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="slots",
                        to="doctors.doctor",
                    ),
                ),
            ],
            options={
                "ordering": ["start_time"],
                "indexes": [
                    models.Index(
                        fields=["doctor", "start_time"], name="slot_doctor_start_idx"
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("end_time__gt", models.F("start_time"))),
                        name="slot_end_after_start",
                    ),
                    django.contrib.postgres.constraints.ExclusionConstraint(
                        expressions=[
                            ("doctor", "="),
                            (
                                models.Func(
                                    "start_time", "end_time", function="tstzrange"
                                ),
                                "&&",
                            ),
                        ],
                        name="slot_no_overlap_per_doctor",
                    ),
                ],
            },
        ),
    ]
