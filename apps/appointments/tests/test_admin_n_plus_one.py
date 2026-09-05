"""Проверка отсутствия регрессии N+1 в списке записей администратора.

Количество запросов сравнивается для 3 и 12 записей. При корректном
использовании select_related оно не должно зависеть от числа строк.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_admin, make_doctor_user, make_patient
from apps.slots.models import Slot


class AdminAppointmentsNPlusOneTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _create_appointments(self, count, offset=0):
        base = timezone.now() + timedelta(days=5)
        for i in range(offset, offset + count):
            _, doctor = make_doctor_user(username=f"n1_doctor_{i}")
            patient = make_patient(username=f"n1_patient_{i}")
            start = base + timedelta(hours=i)
            slot = Slot.objects.create(doctor=doctor, start_time=start, end_time=start + timedelta(minutes=30))
            Appointment.objects.create(
                slot=slot, patient=patient, start_time=slot.start_time, end_time=slot.end_time,
                status=Appointment.Status.BOOKED,
            )

    def test_query_count_does_not_scale_with_result_count(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._create_appointments(3)
        with CaptureQueriesContext(connection) as small:
            response_small = self.client.get("/api/admin/appointments/")
        self.assertEqual(response_small.status_code, 200)

        self._create_appointments(9, offset=3)  # Всего теперь 12 записей.
        with CaptureQueriesContext(connection) as large:
            response_large = self.client.get("/api/admin/appointments/")
        self.assertEqual(response_large.status_code, 200)

        self.assertEqual(
            len(small.captured_queries),
            len(large.captured_queries),
            "Query count grew with the number of appointments -- N+1 regression. "
            f"3 appointments -> {len(small.captured_queries)} queries, "
            f"12 appointments -> {len(large.captured_queries)} queries.",
        )
