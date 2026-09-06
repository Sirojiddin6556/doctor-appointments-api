"""Пользователь с ролью doctor, но без Doctor-профиля, не должен ломать API.

Такое состояние возможно, если роль назначили, а профиль ещё не создали.
Эндпоинты врача обязаны отвечать понятным 403, а не 500.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.users.models import User


class DoctorWithoutProfileTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="orphan_doctor", password="TestPass123!", role=User.Role.DOCTOR
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_create_slots_returns_403_not_500(self):
        start = timezone.now() + timedelta(days=1)
        response = self.client.post(
            "/api/slots/",
            {"start_time": start.isoformat(), "end_time": (start + timedelta(hours=1)).isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_schedule_returns_403_not_500(self):
        response = self.client.get("/api/slots/mine/")
        self.assertEqual(response.status_code, 403)
