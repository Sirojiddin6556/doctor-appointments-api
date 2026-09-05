from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import RangeOperators
from django.db import models
from django.db.models import CheckConstraint, F, Q
from django.utils import timezone

from apps.slots.models import Slot


class Appointment(models.Model):
    """
    A patient's booking of a Slot.

    `slot` is a plain ForeignKey (not OneToOne): a slot's history can contain
    several Appointment rows over time (booked -> cancelled -> booked again by
    someone else). What must never happen is *two simultaneously-active*
    bookings on the same slot — that is enforced by the partial unique
    constraint below, not by the FK shape.

    start_time/end_time are copied from the Slot at booking time. This is a
    deliberate denormalization: PostgreSQL's ExcludeConstraint (used below to
    stop a patient double-booking overlapping times, rule 3) can only operate
    on columns of the table it's declared on, not across a join to Slot.
    Since an appointment's time cannot change after creation (cancelling
    creates no new time, rebooking creates a new row), this copy never goes
    stale.
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
            # Rule 1: a slot can never have two simultaneously-active bookings.
            # This is the primary, DB-level defense against the race condition
            # the brief explicitly asks about. The view *additionally* takes a
            # row lock (select_for_update) on the Slot to turn the resulting
            # IntegrityError into a clean 400 instead of a 500.
            models.UniqueConstraint(
                fields=["slot"],
                condition=Q(status="booked"),
                name="unique_active_booking_per_slot",
            ),
            # Rule 3: a patient cannot have two overlapping *booked* appointments.
            # Postgres range-overlap exclusion constraint, scoped to booked rows.
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
