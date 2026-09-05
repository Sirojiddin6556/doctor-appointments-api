"""
Rule 2: "O'tib ketgan vaqtdagi slotni band qilib bo'lmaydi."
Rule 3: "Bemorda vaqti ustma-ust tushadigan ikkita booked navbat bo'lmasin."
"""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_doctor_user, make_patient
from apps.slots.models import Slot


class NoPastBookingTest(TestCase):
    def setUp(self):
        _, self.doctor = make_doctor_user()
        self.patient = make_patient()
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

    def test_cannot_book_a_slot_that_already_started(self):
        past_slot = Slot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() - timedelta(minutes=30),
        )

        response = self.client.post("/api/appointments/", {"slot": past_slot.id}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Appointment.objects.filter(slot=past_slot).exists())

    def test_can_book_a_future_slot(self):
        future_slot = Slot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1, minutes=30),
        )

        response = self.client.post("/api/appointments/", {"slot": future_slot.id}, format="json")

        self.assertEqual(response.status_code, 201, response.data)


class NoOverlappingPatientBookingsTest(TestCase):
    def setUp(self):
        _, self.doctor_a = make_doctor_user(username="doc_a")
        _, self.doctor_b = make_doctor_user(username="doc_b")
        self.patient = make_patient()
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

        start = timezone.now() + timedelta(hours=3)
        self.slot_a = Slot.objects.create(doctor=self.doctor_a, start_time=start, end_time=start + timedelta(minutes=30))
        # Overlaps slot_a by 15 minutes, different doctor.
        overlap_start = start + timedelta(minutes=15)
        self.slot_b = Slot.objects.create(
            doctor=self.doctor_b, start_time=overlap_start, end_time=overlap_start + timedelta(minutes=30)
        )
        # Does not overlap slot_a at all.
        later_start = start + timedelta(hours=2)
        self.slot_c = Slot.objects.create(
            doctor=self.doctor_b, start_time=later_start, end_time=later_start + timedelta(minutes=30)
        )

    def test_overlapping_booking_is_rejected(self):
        first = self.client.post("/api/appointments/", {"slot": self.slot_a.id}, format="json")
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post("/api/appointments/", {"slot": self.slot_b.id}, format="json")
        self.assertEqual(second.status_code, 400)

    def test_non_overlapping_booking_is_allowed(self):
        first = self.client.post("/api/appointments/", {"slot": self.slot_a.id}, format="json")
        self.assertEqual(first.status_code, 201, first.data)

        second = self.client.post("/api/appointments/", {"slot": self.slot_c.id}, format="json")
        self.assertEqual(second.status_code, 201, second.data)

    def test_db_exclusion_constraint_is_the_final_authority(self):
        """Even bypassing the view's application-level overlap check, the
        database itself must refuse two overlapping booked appointments for
        the same patient."""
        Appointment.objects.create(
            slot=self.slot_a, patient=self.patient,
            start_time=self.slot_a.start_time, end_time=self.slot_a.end_time,
            status=Appointment.Status.BOOKED,
        )

        with self.assertRaises(IntegrityError), transaction.atomic():
            Appointment.objects.create(
                slot=self.slot_b, patient=self.patient,
                start_time=self.slot_b.start_time, end_time=self.slot_b.end_time,
                status=Appointment.Status.BOOKED,
            )
