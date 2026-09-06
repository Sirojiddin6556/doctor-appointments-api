"""
Rule 4: "Bekor qilish faqat slot boshlanishiga 2 soatdan ko'proq vaqt
qolganda mumkin. Kechroq bo'lsa — 400 va aniq xabar."
Правило 5: после отмены слот снова становится доступен для бронирования.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_doctor_user, make_patient
from apps.slots.models import Slot


class CancellationWindowTest(TestCase):
    def setUp(self):
        _, self.doctor = make_doctor_user()
        self.patient = make_patient()
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

    def _book(self, start_delta, end_delta=None):
        slot = Slot.objects.create(
            doctor=self.doctor,
            start_time=timezone.now() + start_delta,
            end_time=timezone.now() + (end_delta or start_delta + timedelta(minutes=30)),
        )
        appointment = Appointment.objects.create(
            slot=slot,
            patient=self.patient,
            start_time=slot.start_time,
            end_time=slot.end_time,
            status=Appointment.Status.BOOKED,
        )
        return slot, appointment

    def test_cancel_more_than_2_hours_before_start_succeeds(self):
        _slot, appointment = self._book(timedelta(hours=3))

        response = self.client.post(f"/api/appointments/{appointment.id}/cancel/")

        self.assertEqual(response.status_code, 200, response.data)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.CANCELLED)
        self.assertIsNotNone(appointment.cancelled_at)

    def test_cancel_less_than_2_hours_before_start_is_rejected(self):
        _slot, appointment = self._book(timedelta(minutes=90))

        response = self.client.post(f"/api/appointments/{appointment.id}/cancel/")

        self.assertEqual(response.status_code, 400)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, Appointment.Status.BOOKED, "Must NOT be cancelled.")

    def test_cancel_exactly_at_2_hour_boundary_is_rejected(self):
        # По правилу ровно 2 часа до начала недостаточно для отмены.
        _slot, appointment = self._book(timedelta(hours=2))

        response = self.client.post(f"/api/appointments/{appointment.id}/cancel/")

        self.assertEqual(response.status_code, 400)

    def test_cancelling_frees_the_slot_for_rebooking(self):
        slot, appointment = self._book(timedelta(hours=3))
        self.client.post(f"/api/appointments/{appointment.id}/cancel/")

        other_patient = make_patient(username="other_patient")
        other_client = APIClient()
        other_client.force_authenticate(other_patient)

        response = other_client.post("/api/appointments/", {"slot": slot.id}, format="json")

        self.assertEqual(response.status_code, 201, response.data)

    def test_cannot_cancel_an_already_cancelled_appointment(self):
        _slot, appointment = self._book(timedelta(hours=3))
        appointment.status = Appointment.Status.CANCELLED
        appointment.save(update_fields=["status"])

        response = self.client.post(f"/api/appointments/{appointment.id}/cancel/")

        self.assertEqual(response.status_code, 400)
