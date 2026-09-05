"""
Rule 1: "Bitta slot hech qachon ikki marta band qilinmasin."

Of several concurrent booking requests for the same slot, exactly one must
succeed and the rest must fail with a clean 4xx — never two bookings, never
an unhandled 500.
"""

import threading
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.common.test_utils import make_doctor_user, make_patient
from apps.slots.models import Slot


class SlotDoubleBookingRaceTest(TransactionTestCase):
    """
    Uses TransactionTestCase (not TestCase) on purpose: this test exercises
    real, separately-committed transactions racing each other through
    select_for_update(). A plain TestCase wraps the whole test in one
    uncommitted outer transaction, which would hide the very row-locking
    behavior under test and make every thread see the same in-memory state.
    """

    N_PATIENTS = 10

    def setUp(self):
        _, self.doctor = make_doctor_user(username="race_doctor")
        self.slot = Slot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, minutes=30),
        )
        self.patients = [make_patient(username=f"racer{i}") for i in range(self.N_PATIENTS)]

    def _book(self, user, results, index):
        try:
            client = APIClient()
            token = str(RefreshToken.for_user(user).access_token)
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            response = client.post("/api/appointments/", {"slot": self.slot.id}, format="json")
            results[index] = response.status_code
        finally:
            # Each thread gets its own thread-local DB connection (that's
            # the whole point of this test); Django won't close it for us
            # when a plain threading.Thread finishes, so we do it explicitly
            # to avoid leaking connections into the test-database teardown.
            connection.close()

    def test_exactly_one_booking_wins_under_concurrency(self):
        results = [None] * self.N_PATIENTS
        threads = [
            threading.Thread(target=self._book, args=(patient, results, i))
            for i, patient in enumerate(self.patients)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertNotIn(500, results, f"A request crashed with a 500: {results}")
        self.assertEqual(results.count(201), 1, f"Expected exactly one 201, got: {results}")
        self.assertEqual(
            results.count(400), self.N_PATIENTS - 1, f"Expected the rest to be 400, got: {results}"
        )
        self.assertEqual(
            Appointment.objects.filter(slot=self.slot, status=Appointment.Status.BOOKED).count(),
            1,
            "Exactly one BOOKED appointment must exist for the slot after the race.",
        )


class SlotUniqueConstraintDefenseInDepthTest(TransactionTestCase):
    """
    Even if a future code change removed the select_for_update() lock in the
    view, the database itself must still refuse a second active booking on
    the same slot. This test bypasses the view/lock entirely and inserts
    directly through the ORM to prove the guarantee lives in the schema,
    not only in application code.
    """

    def setUp(self):
        _, self.doctor = make_doctor_user(username="constraint_doctor")
        self.slot = Slot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + timedelta(days=1),
            end_time=timezone.now() + timedelta(days=1, minutes=30),
        )
        self.patient_a = make_patient(username="constraint_patient_a")
        self.patient_b = make_patient(username="constraint_patient_b")

    def test_second_direct_insert_is_rejected_by_db_constraint(self):
        Appointment.objects.create(
            slot=self.slot,
            patient=self.patient_a,
            start_time=self.slot.start_time,
            end_time=self.slot.end_time,
            status=Appointment.Status.BOOKED,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                slot=self.slot,
                patient=self.patient_b,
                start_time=self.slot.start_time,
                end_time=self.slot.end_time,
                status=Appointment.Status.BOOKED,
            )

        self.assertEqual(
            Appointment.objects.filter(slot=self.slot, status=Appointment.Status.BOOKED).count(), 1
        )
