"""
Rule 6: "Shifokor faqat o'zining slotlarini ko'radi va o'zgartiradi. Bemor
faqat o'zining navbatlarini ko'radi va bekor qiladi. Buni frontendda emas,
API tomonida ta'minlang."
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_admin, make_doctor_user, make_patient
from apps.slots.models import Slot


class PatientCanOnlySeeOwnAppointmentsTest(TestCase):
    def setUp(self):
        _, doctor = make_doctor_user()
        self.slot_a = Slot.objects.create(
            doctor=doctor, start_time=timezone.now() + timedelta(hours=3),
            end_time=timezone.now() + timedelta(hours=3, minutes=30),
        )
        self.slot_b = Slot.objects.create(
            doctor=doctor, start_time=timezone.now() + timedelta(hours=5),
            end_time=timezone.now() + timedelta(hours=5, minutes=30),
        )
        self.patient_a = make_patient(username="patient_a")
        self.patient_b = make_patient(username="patient_b")
        self.appt_a = Appointment.objects.create(
            slot=self.slot_a, patient=self.patient_a,
            start_time=self.slot_a.start_time, end_time=self.slot_a.end_time,
            status=Appointment.Status.BOOKED,
        )
        self.appt_b = Appointment.objects.create(
            slot=self.slot_b, patient=self.patient_b,
            start_time=self.slot_b.start_time, end_time=self.slot_b.end_time,
            status=Appointment.Status.BOOKED,
        )

    def test_list_only_returns_own_appointments(self):
        client = APIClient()
        client.force_authenticate(self.patient_a)

        response = client.get("/api/appointments/")

        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [self.appt_a.id])

    def test_cannot_cancel_another_patients_appointment(self):
        client = APIClient()
        client.force_authenticate(self.patient_b)

        response = client.post(f"/api/appointments/{self.appt_a.id}/cancel/")

        # Возвращаем 404, а не 403: объект отсутствует в queryset пациента B,
        # поэтому API не раскрывает сам факт существования чужой записи.
        self.assertEqual(response.status_code, 404)
        self.appt_a.refresh_from_db()
        self.assertEqual(self.appt_a.status, Appointment.Status.BOOKED)


class DoctorCanOnlySeeOwnSlotsTest(TestCase):
    def setUp(self):
        self.doctor_a_user, self.doctor_a = make_doctor_user(username="doctor_a")
        self.doctor_b_user, self.doctor_b = make_doctor_user(username="doctor_b")
        self.slot_a = Slot.objects.create(
            doctor=self.doctor_a, start_time=timezone.now() + timedelta(hours=3),
            end_time=timezone.now() + timedelta(hours=3, minutes=30),
        )
        self.slot_b = Slot.objects.create(
            doctor=self.doctor_b, start_time=timezone.now() + timedelta(hours=4),
            end_time=timezone.now() + timedelta(hours=4, minutes=30),
        )

    def test_mine_only_returns_own_slots(self):
        client = APIClient()
        client.force_authenticate(self.doctor_a_user)

        response = client.get("/api/slots/mine/")

        ids = [item["id"] for item in response.data["results"]]
        self.assertEqual(ids, [self.slot_a.id])
        self.assertNotIn(self.slot_b.id, ids)


class RoleGatingTest(TestCase):
    """Пациент и врач не могут использовать чужие endpoint-ы.

    Административный endpoint доступен только администратору.
    """

    def setUp(self):
        self.patient = make_patient()
        self.doctor_user, _ = make_doctor_user()
        self.admin = make_admin()

    def test_patient_cannot_create_slots(self):
        client = APIClient()
        client.force_authenticate(self.patient)

        response = client.post(
            "/api/slots/",
            {
                "start_time": (timezone.now() + timedelta(days=1)).isoformat(),
                "end_time": (timezone.now() + timedelta(days=1, hours=1)).isoformat(),
                "slot_duration_minutes": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_doctor_cannot_book_appointments(self):
        client = APIClient()
        client.force_authenticate(self.doctor_user)

        response = client.get("/api/appointments/")

        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_access_admin_appointments(self):
        client = APIClient()
        client.force_authenticate(self.patient)

        response = client.get("/api/admin/appointments/")

        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_admin_appointments(self):
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.get("/api/admin/appointments/")

        self.assertEqual(response.status_code, 200)

    def test_anonymous_request_is_rejected(self):
        client = APIClient()

        response = client.get("/api/appointments/")

        self.assertEqual(response.status_code, 401)
