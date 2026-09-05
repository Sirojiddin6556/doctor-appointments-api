"""
Rule 8: "Barcha vaqtlar UTC'da saqlansin va qaytarilsin; API ISO 8601
formatini (timezone bilan) qabul qilsin."
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.common.test_utils import make_doctor_user
from apps.slots.models import Slot


class UtcStorageAndIso8601InputTest(TestCase):
    def setUp(self):
        self.doctor_user, self.doctor = make_doctor_user()
        self.client = APIClient()
        self.client.force_authenticate(self.doctor_user)

    def test_non_utc_offset_input_is_converted_and_stored_as_utc(self):
        # 14:00 в UTC+05:00 (Ташкент) соответствует 09:00 UTC.
        local_start = (timezone.now() + timedelta(days=1)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        start_str = local_start.strftime("%Y-%m-%dT%H:%M:%S+05:00")
        end_str = local_start.replace(hour=16).strftime("%Y-%m-%dT%H:%M:%S+05:00")

        response = self.client.post(
            "/api/slots/",
            {"start_time": start_str, "end_time": end_str, "slot_duration_minutes": 60},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        slot = Slot.objects.get(pk=response.data[0]["id"])
        self.assertEqual(slot.start_time.utcoffset(), timedelta(0))
        self.assertEqual(slot.start_time.hour, 9)  # 14:00+05:00 -> 09:00 UTC.

    def test_response_datetimes_are_iso8601_with_utc_offset(self):
        start = (timezone.now() + timedelta(days=1)).replace(minute=0, second=0, microsecond=0)
        Slot.objects.create(doctor=self.doctor, start_time=start, end_time=start + timedelta(minutes=30))

        response = self.client.get("/api/slots/mine/")

        returned = response.data["results"][0]["start_time"]
        # Формат ISO 8601 от DRF заканчивается символом "Z" для UTC.
        self.assertTrue(returned.endswith("Z"), f"Expected UTC 'Z' suffix, got: {returned}")
