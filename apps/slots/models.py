from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import models
from django.db.models import CheckConstraint, F, Q
from django.utils import timezone

from apps.doctors.models import Doctor


class Slot(models.Model):
    """Временной интервал, в который врач доступен для записи.

    Свободность вычисляется по активным Appointment и не хранится отдельным
    флагом, поэтому состояние слота не рассинхронизируется после отмены.
    """

    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE, related_name="slots")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["doctor", "start_time"], name="slot_doctor_start_idx"),
        ]
        constraints = [
            CheckConstraint(
                check=Q(end_time__gt=F("start_time")),
                name="slot_end_after_start",
            ),
            # Правило 7: у одного врача не бывает пересекающихся слотов.
            ExclusionConstraint(
                name="slot_no_overlap_per_doctor",
                expressions=[
                    ("doctor", RangeOperators.EQUAL),
                    (
                        models.Func(
                            "start_time",
                            "end_time",
                            function="tstzrange",
                        ),
                        RangeOperators.OVERLAPS,
                    ),
                ],
            ),
        ]

    def __str__(self) -> str:
        return f"{self.doctor} | {self.start_time.isoformat()} - {self.end_time.isoformat()}"

    @property
    def is_in_past(self) -> bool:
        return self.start_time <= timezone.now()

    @property
    def active_appointment(self):
        """Вернуть активную запись слота, если она существует.

        Перебор `.all()` использует кэш `prefetch_related` и не создает
        дополнительные запросы при выдаче большого списка слотов.
        """
        for appointment in self.appointments.all():
            if appointment.status == "booked":
                return appointment
        return None

    @property
    def is_free(self) -> bool:
        return self.active_appointment is None
