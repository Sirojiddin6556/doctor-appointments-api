"""Правило 5: отменённый слот снова становится свободным и его можно
забронировать заново.

Свободность слота нигде не хранится отдельным флагом — она вычисляется по
отсутствию активной (`booked`) записи. Поэтому после отмены слот обязан
сразу вернуться и в выдачу свободных слотов, и быть доступным для новой
брони — в том числе другим пациентом и тем же пациентом повторно.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.appointments.models import Appointment
from apps.common.test_utils import make_doctor_user, make_patient
from apps.slots.models import Slot


def _client(user):
    client = APIClient()
    token = str(RefreshToken.for_user(user).access_token)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


class SlotReopensAfterCancellationTest(TestCase):
    def setUp(self):
        _, self.doctor = make_doctor_user(username="reopen_doctor")
        # Более чем за 2 часа до начала, иначе отмена запрещена правилом 4.
        self.start = timezone.now() + timedelta(days=1)
        self.slot = Slot.objects.create(
            doctor=self.doctor, start_time=self.start, end_time=self.start + timedelta(minutes=30)
        )
        self.patient_a = make_patient(username="reopen_a")
        self.patient_b = make_patient(username="reopen_b")

    def _book(self, patient):
        return _client(patient).post("/api/appointments/", {"slot": self.slot.id}, format="json")

    def _cancel(self, patient, appointment_id):
        return _client(patient).post(f"/api/appointments/{appointment_id}/cancel/")

    def test_slot_is_not_free_while_booked_then_free_after_cancel(self):
        booking = self._book(self.patient_a)
        self.assertEqual(booking.status_code, 201, booking.data)

        self.slot.refresh_from_db()
        self.assertFalse(self.slot.is_free)
        free_before = _client(self.patient_b).get(
            f"/api/doctors/{self.doctor.id}/slots/?date={self.start.date()}"
        )
        self.assertNotIn(self.slot.id, [s["id"] for s in free_before.data])

        cancel = self._cancel(self.patient_a, booking.data["id"])
        self.assertEqual(cancel.status_code, 200, cancel.data)

        self.slot.refresh_from_db()
        self.assertTrue(self.slot.is_free)
        free_after = _client(self.patient_b).get(
            f"/api/doctors/{self.doctor.id}/slots/?date={self.start.date()}"
        )
        self.assertIn(self.slot.id, [s["id"] for s in free_after.data])

    def test_another_patient_can_book_the_freed_slot(self):
        booking = self._book(self.patient_a)
        self._cancel(self.patient_a, booking.data["id"])

        rebooking = self._book(self.patient_b)

        self.assertEqual(rebooking.status_code, 201, rebooking.data)
        self.assertEqual(
            Appointment.objects.filter(slot=self.slot, status=Appointment.Status.BOOKED).count(), 1
        )

    def test_same_patient_can_rebook_the_freed_slot(self):
        booking = self._book(self.patient_a)
        self._cancel(self.patient_a, booking.data["id"])

        rebooking = self._book(self.patient_a)

        self.assertEqual(rebooking.status_code, 201, rebooking.data)
        self.assertEqual(
            Appointment.objects.filter(slot=self.slot, status=Appointment.Status.BOOKED).count(), 1
        )
        # История сохраняется: одна отменённая + одна активная запись.
        self.assertEqual(Appointment.objects.filter(slot=self.slot).count(), 2)

    def test_cannot_double_cancel(self):
        booking = self._book(self.patient_a)
        first = self._cancel(self.patient_a, booking.data["id"])
        self.assertEqual(first.status_code, 200)

        second = self._cancel(self.patient_a, booking.data["id"])
        self.assertEqual(second.status_code, 400)
