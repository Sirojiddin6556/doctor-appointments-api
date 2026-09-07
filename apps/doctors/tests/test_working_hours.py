"""Самообслуживание графика: GET/PUT /api/doctors/me/working-hours/."""

from datetime import time

from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.test_utils import make_doctor_user, make_patient
from apps.doctors.models import DoctorWorkingHours


class DoctorWorkingHoursSelfServiceTest(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor = make_doctor_user(with_working_hours=False)
        self.client = APIClient()
        self.client.force_authenticate(self.doctor_user)

    def test_no_schedule_returns_seven_days_off(self):
        response = self.client.get("/api/doctors/me/working-hours/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 7)
        self.assertTrue(all(day["is_working_day"] is False for day in response.data))

    def test_put_replaces_schedule(self):
        payload = [
            {"weekday": 0, "start_time": "09:00", "end_time": "18:00", "break_start": "13:00", "break_end": "14:00"},
            {"weekday": 5, "start_time": "09:00", "end_time": "13:00"},
        ]

        response = self.client.put("/api/doctors/me/working-hours/", payload, format="json")

        self.assertEqual(response.status_code, 200, response.data)
        by_weekday = {day["weekday"]: day for day in response.data}
        self.assertTrue(by_weekday[0]["is_working_day"])
        self.assertEqual(by_weekday[0]["break_start"], time(13, 0))
        self.assertTrue(by_weekday[5]["is_working_day"])
        self.assertIsNone(by_weekday[5]["break_start"])
        # Воскресенье не перечислено в payload -> остаётся выходным.
        self.assertFalse(by_weekday[6]["is_working_day"])
        self.assertEqual(DoctorWorkingHours.objects.filter(doctor=self.doctor).count(), 2)

    def test_put_is_a_full_replace_not_a_merge(self):
        DoctorWorkingHours.objects.create(doctor=self.doctor, weekday=1, start_time=time(9, 0), end_time=time(17, 0))

        # Новый PUT не содержит понедельник (weekday=1) -> старая запись должна исчезнуть.
        response = self.client.put(
            "/api/doctors/me/working-hours/",
            [{"weekday": 2, "start_time": "09:00", "end_time": "17:00"}],
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(DoctorWorkingHours.objects.filter(doctor=self.doctor).count(), 1)
        self.assertFalse(DoctorWorkingHours.objects.filter(doctor=self.doctor, weekday=1).exists())

    def test_break_outside_working_hours_is_rejected(self):
        response = self.client.put(
            "/api/doctors/me/working-hours/",
            [{"weekday": 0, "start_time": "09:00", "end_time": "18:00", "break_start": "08:00", "break_end": "08:30"}],
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(DoctorWorkingHours.objects.filter(doctor=self.doctor).count(), 0)

    def test_end_before_start_is_rejected(self):
        response = self.client.put(
            "/api/doctors/me/working-hours/",
            [{"weekday": 0, "start_time": "18:00", "end_time": "09:00"}],
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_duplicate_weekday_in_payload_is_rejected(self):
        response = self.client.put(
            "/api/doctors/me/working-hours/",
            [
                {"weekday": 0, "start_time": "09:00", "end_time": "13:00"},
                {"weekday": 0, "start_time": "14:00", "end_time": "18:00"},
            ],
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_patient_cannot_access_doctor_working_hours(self):
        patient = make_patient()
        client = APIClient()
        client.force_authenticate(patient)

        response = client.get("/api/doctors/me/working-hours/")

        self.assertEqual(response.status_code, 403)
