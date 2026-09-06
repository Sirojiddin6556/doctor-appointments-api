"""Фильтры админского списка записей и фильтр по статусу у пациента."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_admin, make_doctor_user, make_patient
from apps.slots.models import Slot


class AdminAppointmentFiltersTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

        _, self.cardio = make_doctor_user(username="f_cardio", specialization="Cardiology", branch="Central")
        _, self.neuro = make_doctor_user(username="f_neuro", specialization="Neurology", branch="North")
        self.patient = make_patient(username="f_patient")

        base = timezone.now() + timedelta(days=2)
        self.appt_cardio = self._appointment(self.cardio, base)
        self.appt_neuro = self._appointment(self.neuro, base + timedelta(days=5))

    def _appointment(self, doctor, start):
        slot = Slot.objects.create(doctor=doctor, start_time=start, end_time=start + timedelta(minutes=30))
        return Appointment.objects.create(
            slot=slot, patient=self.patient, start_time=slot.start_time,
            end_time=slot.end_time, status=Appointment.Status.BOOKED,
        )

    def _ids(self, response):
        return {row["id"] for row in response.data["results"]}

    def test_filter_by_doctor(self):
        response = self.client.get(f"/api/admin/appointments/?doctor={self.cardio.id}")
        self.assertEqual(self._ids(response), {self.appt_cardio.id})

    def test_filter_by_branch(self):
        response = self.client.get("/api/admin/appointments/?branch=North")
        self.assertEqual(self._ids(response), {self.appt_neuro.id})

    def test_filter_by_date_range(self):
        cutoff = (self.appt_cardio.start_time + timedelta(days=1)).date()
        response = self.client.get(f"/api/admin/appointments/?date_to={cutoff}")
        self.assertEqual(self._ids(response), {self.appt_cardio.id})

    def test_admin_can_force_cancel_regardless_of_2h_window(self):
        # Приём начинается меньше чем через 2 часа — пациенту отмена запрещена,
        # админу разрешена.
        soon = timezone.now() + timedelta(minutes=30)
        appt = self._appointment(self.cardio, soon)

        response = self.client.post(f"/api/admin/appointments/{appt.id}/cancel/")

        self.assertEqual(response.status_code, 200, response.data)
        appt.refresh_from_db()
        self.assertEqual(appt.status, Appointment.Status.CANCELLED)
        self.assertIsNotNone(appt.cancelled_at)


class PatientStatusFilterTest(TestCase):
    def setUp(self):
        _, doctor = make_doctor_user(username="s_doctor")
        self.patient = make_patient(username="s_patient")
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

        base = timezone.now() + timedelta(days=3)
        self.booked = self._appointment(doctor, base, Appointment.Status.BOOKED)
        self.cancelled = self._appointment(doctor, base + timedelta(hours=2), Appointment.Status.CANCELLED)

    def _appointment(self, doctor, start, status):
        slot = Slot.objects.create(doctor=doctor, start_time=start, end_time=start + timedelta(minutes=30))
        return Appointment.objects.create(
            slot=slot, patient=self.patient, start_time=slot.start_time,
            end_time=slot.end_time, status=status,
        )

    def test_no_filter_returns_all_history(self):
        response = self.client.get("/api/appointments/")
        self.assertEqual({r["id"] for r in response.data["results"]}, {self.booked.id, self.cancelled.id})

    def test_status_filter_narrows_result(self):
        response = self.client.get("/api/appointments/?status=booked")
        self.assertEqual({r["id"] for r in response.data["results"]}, {self.booked.id})
