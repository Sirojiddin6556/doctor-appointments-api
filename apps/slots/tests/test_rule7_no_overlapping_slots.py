"""Правило 7: врач не может создать пересекающийся со своим слот."""

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.test_utils import make_doctor_user
from apps.slots.models import Slot


class DoctorSlotOverlapTest(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor = make_doctor_user()
        self.client = APIClient()
        self.client.force_authenticate(self.doctor_user)

    def test_bulk_create_generates_expected_slots(self):
        start = timezone.now() + timedelta(days=1)
        start = start.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)

        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": end.isoformat(), "slot_duration_minutes": 30},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data), 4)  # 2 часа по 30 минут.
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 4)

    def test_creating_an_overlapping_slot_is_rejected_and_atomic(self):
        start = timezone.now() + timedelta(days=1)
        Slot.objects.create(doctor=self.doctor, start_time=start, end_time=start + timedelta(hours=1))

        # Первый слот нового пакета полностью пересекается с существующим.
        response = self.client.post(
            "/api/slots/",
            {
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=2)).isoformat(),
                "slot_duration_minutes": 30,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        # Атомарность: ни один слот нового пакета не создан.
        self.assertEqual(Slot.objects.filter(doctor=self.doctor).count(), 1)

    def test_db_exclusion_constraint_is_the_final_authority(self):
        start = timezone.now() + timedelta(days=1)
        Slot.objects.create(doctor=self.doctor, start_time=start, end_time=start + timedelta(minutes=30))

        with self.assertRaises(IntegrityError), transaction.atomic():
            Slot.objects.create(
                doctor=self.doctor,
                start_time=start + timedelta(minutes=15),
                end_time=start + timedelta(minutes=45),
            )

    def test_different_doctors_can_have_overlapping_slots(self):
        _other_user, other_doctor = make_doctor_user(username="other_doc")
        start = timezone.now() + timedelta(days=1)
        Slot.objects.create(doctor=self.doctor, start_time=start, end_time=start + timedelta(minutes=30))

        # Исключение не ожидается: правило действует отдельно для каждого врача.
        Slot.objects.create(doctor=other_doctor, start_time=start, end_time=start + timedelta(minutes=30))

        self.assertEqual(Slot.objects.count(), 2)
