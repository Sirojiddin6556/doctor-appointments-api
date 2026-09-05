from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import models
from django.db.models import CheckConstraint, F, Q
from django.utils import timezone

from apps.doctors.models import Doctor


class Slot(models.Model):
    """
    A time window during which a doctor is available.

    "Free" is *derived*, not stored: a slot is free iff it has no related
    Appointment with status='booked'. See Slot.is_free / SlotQuerySet.free().
    Storing a redundant `is_booked` boolean would risk drifting out of sync
    with the actual Appointment rows (e.g. after a cancellation) — a single
    source of truth is safer for data integrity (criterion #4 in the brief).
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
            # Rule 7: a doctor cannot have two overlapping slots of their own.
            # Enforced at the database level (Postgres range-overlap exclusion),
            # so it holds even under concurrent slot-creation requests.
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
        """
        Returns the booked Appointment for this slot, if any.

        Deliberately iterates over `self.appointments.all()` in Python
        instead of `self.appointments.filter(status="booked").first()`:
        the `.filter()` form always issues a fresh query, which defeats a
        `prefetch_related("appointments")` upstream and reintroduces N+1
        queries when listing many slots (e.g. GET /api/slots/mine/,
        GET /api/admin/appointments/). Iterating over `.all()` reuses the
        prefetch cache when the caller set one up.
        """
        for appointment in self.appointments.all():
            if appointment.status == "booked":
                return appointment
        return None

    @property
    def is_free(self) -> bool:
        return self.active_appointment is None
