from django.conf import settings
from django.db import models


class Doctor(models.Model):
    """Профиль врача, связанный с пользователем отношением один-к-одному.

    Специализация и филиал хранятся в индексированных строковых полях:
    отдельные справочники не нужны в рамках текущего задания.
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
