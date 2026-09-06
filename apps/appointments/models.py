from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import models
from django.db.models import CheckConstraint, F, Q
from django.utils import timezone

from apps.slots.models import Slot


class Appointment(models.Model):
    """Запись пациента на временной интервал слота.

    Обычный внешний ключ позволяет хранить историю: отмененная запись может
    быть заменена новой. Частичное уникальное ограничение запрещает только
    две активные записи. Время копируется из Slot, чтобы ограничение
    пересечений PostgreSQL применялось непосредственно к этой таблице.
    """

    class Status(models.TextChoices):
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"
        COMPLETED = "completed", "Completed"

    slot = models.ForeignKey(Slot, on_delete=models.PROTECT, related_name="appointments")
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments"
    )
    start_time = models.DateTimeField(help_text="Copied from slot.start_time at booking time.")
    end_time = models.DateTimeField(help_text="Copied from slot.end_time at booking time.")
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.BOOKED, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["patient", "status"], name="appt_patient_status_idx"),
            models.Index(fields=["status", "start_time"], name="appt_status_start_idx"),
        ]
        constraints = [
            CheckConstraint(
                check=Q(end_time__gt=F("start_time")),
                name="appointment_end_after_start",
            ),
            # Правило 1: у слота не может быть двух активных записей.
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(status="booked"),
                name="unique_active_booking_per_slot",
            ),
            # Правило 3: активные записи одного пациента не могут пересекаться.
            ExclusionConstraint(
                name="appointment_no_overlap_per_patient",
                expressions=[
                    ("patient", RangeOperators.EQUAL),
                    (
                        models.Func("start_time", "end_time", function="tstzrange"),
                        RangeOperators.OVERLAPS,
                    ),
                ],
                condition=Q(status="booked"),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.patient} @ {self.start_time.isoformat()} [{self.status}]"

    @property
    def can_be_cancelled(self) -> bool:
        if self.status != self.Status.BOOKED:
            return False
        from datetime import timedelta

        return self.start_time - timezone.now() > timedelta(hours=2)
