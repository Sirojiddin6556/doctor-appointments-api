from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q


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


class DoctorWorkingHours(models.Model):
    """Рабочее время врача на один день недели, с необязательным обедом.

    Отсутствие записи для дня недели означает выходной: `POST /api/slots/`
    не даст создать слот в этот день (график обязателен — см. apps/slots/views.py).
    Управляет своим графиком сам врач через `/api/doctors/me/working-hours/`;
    специализацию и филиал по-прежнему меняет только администратор.
    """

    class Weekday(models.IntegerChoices):
        # Как в datetime.date.weekday(): понедельник — 0, воскресенье — 6.
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="working_hours")
    weekday = models.IntegerField(choices=Weekday.choices)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)

    class Meta:
        ordering = ["doctor_id", "weekday"]
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "weekday"], name="unique_working_hours_per_weekday"
            ),
            CheckConstraint(
                check=Q(end_time__gt=models.F("start_time")),
                name="working_hours_end_after_start",
            ),
            # Обед — либо не задан вовсе (оба поля пустые), либо целиком внутри
            # рабочего окна и с положительной длительностью.
            CheckConstraint(
                check=(
                    (Q(break_start__isnull=True) & Q(break_end__isnull=True))
                    | (
                        Q(break_start__isnull=False)
                        & Q(break_end__isnull=False)
                        & Q(break_end__gt=models.F("break_start"))
                        & Q(break_start__gte=models.F("start_time"))
                        & Q(break_end__lte=models.F("end_time"))
                    )
                ),
                name="working_hours_break_within_bounds",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.doctor} | {self.get_weekday_display()} {self.start_time}-{self.end_time}"
