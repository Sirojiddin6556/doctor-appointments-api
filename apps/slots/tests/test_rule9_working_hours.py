"""Правило 9: слот можно создать только в рабочие часы врача, вне обеда."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.test_utils import make_doctor_user
from apps.doctors.models import DoctorWorkingHours
from apps.slots.models import Slot


def _next_weekday(weekday):
    """Ближайшая (начиная с завтра) дата с нужным datetime.weekday()."""
    day = timezone.now() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day.replace(hour=0, minute=0, second=0, microsecond=0)


class WorkingHoursGateSlotCreationTest(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor = make_doctor_user(with_working_hours=False)
        self.client = APIClient()
        self.client.force_authenticate(self.doctor_user)

    def test_slot_creation_without_any_schedule_is_rejected(self):
        start = _next_weekday(0).replace(hour=10)

        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 0)

    def test_slot_inside_working_hours_is_created(self):
        DoctorWorkingHours.objects.create(doctor=self.doctor, weekday=0, start_time="09:00", end_time="18:00")
        start = _next_weekday(0).replace(hour=10)

        response = self.client.post(
            "/api/slots/",
            {
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=1)).isoformat(),
                "slot_duration_minutes": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 2)

    def test_slot_before_start_of_working_day_is_rejected(self):
        DoctorWorkingHours.objects.create(doctor=self.doctor, weekday=0, start_time="09:00", end_time="18:00")
        start = _next_weekday(0).replace(hour=7)

        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 0)

    def test_slot_after_end_of_working_day_is_rejected(self):
        DoctorWorkingHours.objects.create(doctor=self.doctor, weekday=0, start_time="09:00", end_time="18:00")
        start = _next_weekday(0).replace(hour=17, minute=30)

        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 0)

    def test_slot_overlapping_lunch_break_is_rejected(self):
        DoctorWorkingHours.objects.create(
            doctor=self.doctor, weekday=0, start_time="09:00", end_time="18:00",
            break_start="13:00", break_end="14:00",
        )
        start = _next_weekday(0).replace(hour=12, minute=30)

        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 0)

    def test_slot_right_up_to_lunch_break_boundary_is_allowed(self):
        DoctorWorkingHours.objects.create(
            doctor=self.doctor, weekday=0, start_time="09:00", end_time="18:00",
            break_start="13:00", break_end="14:00",
        )
        start = _next_weekday(0).replace(hour=12, minute=30)
        end = start.replace(hour=13, minute=0)

        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": end.isoformat(), "slot_duration_minutes": 30},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)

    def test_batch_with_one_slot_hitting_lunch_is_rejected_atomically(self):
        DoctorWorkingHours.objects.create(
            doctor=self.doctor, weekday=0, start_time="09:00", end_time="18:00",
            break_start="13:00", break_end="14:00",
        )
        start = _next_weekday(0).replace(hour=12)

        # 12:00-14:30 по 30 минут: слоты 13:00-13:30 и 13:30-14:00 попадают в обед.
        response = self.client.post(
            "/api/slots/",
            {
                "start_time": start.isoformat(),
                "end_time": start.replace(hour=14, minute=30).isoformat(),
                "slot_duration_minutes": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        # Атомарность: ни один слот пакета не создан, включая 12:00-12:30 и 12:30-13:00.
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 0)
