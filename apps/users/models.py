from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model with an explicit business role.

    Design decision: instead of relying only on Django's is_staff/is_superuser
    flags (which are about *Django admin* access), we add an explicit `role`
    field that drives *business* permissions (patient / doctor / admin).
    This keeps permission checks in the API simple and explicit
    ("request.user.role == Role.DOCTOR") instead of overloading is_staff.

    `is_staff`/`is_superuser` are still used for the Django admin site itself,
    completely independent of this field.
    """

    class Role(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.PATIENT,
        db_index=True,
        help_text="Business role used for API permission checks.",
    )

    def __str__(self) -> str:
        return f"{self.username} ({self.role})"

    @property
    def is_patient(self) -> bool:
        return self.role == self.Role.PATIENT

    @property
    def is_doctor_role(self) -> bool:
        return self.role == self.Role.DOCTOR

    @property
    def is_admin_role(self) -> bool:
        return self.role == self.Role.ADMIN
