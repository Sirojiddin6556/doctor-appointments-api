from django.conf import settings
from django.db import models


class Doctor(models.Model):
    """
    Doctor profile, one-to-one with a User whose role == 'doctor'.

    We keep specialization/branch as plain indexed CharFields rather than
    separate FK tables (Specialization, Branch) — the task doesn't require
    managing a catalog of them, and a smaller correct model beats an
    over-engineered one. This is called out in the README as a deliberate
    simplification.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    specialization = models.CharField(max_length=100, db_index=True)
    branch = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Dr. {self.user.get_full_name() or self.user.username} ({self.specialization})"
