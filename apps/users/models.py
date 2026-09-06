from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Пользователь с явной бизнес-ролью пациента, врача или администратора.

    Поля is_staff и is_superuser отвечают только за Django Admin, а проверки
    API используют отдельное поле role.
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
