"""`/api/auth/me/` и `/api/auth/change-password/` — самообслуживание профиля."""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.test_utils import make_doctor_user, make_patient
from apps.users.models import User


class SelfProfileTest(TestCase):
    def setUp(self):
        self.patient = make_patient(username="self_patient", email="patient@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

    def test_get_me_returns_own_profile(self):
        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["username"], "self_patient")
        self.assertEqual(response.data["role"], "patient")

    def test_patch_updates_first_name_and_email(self):
        response = self.client.patch(
            "/api/auth/me/", {"first_name": "Иван", "email": "new@example.com"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.first_name, "Иван")
        self.assertEqual(self.patient.email, "new@example.com")

    def test_patient_cannot_clear_email(self):
        response = self.client.patch("/api/auth/me/", {"email": ""}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_cannot_use_email_already_taken_by_someone_else(self):
        make_patient(username="other_patient", email="taken@example.com")

        response = self.client.patch("/api/auth/me/", {"email": "taken@example.com"}, format="json")

        self.assertEqual(response.status_code, 400)

    def test_role_and_username_are_read_only(self):
        response = self.client.patch(
            "/api/auth/me/", {"role": "admin", "username": "hijacked"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.role, User.Role.PATIENT)
        self.assertEqual(self.patient.username, "self_patient")

    def test_doctor_cannot_self_edit_specialization_or_branch(self):
        doctor_user, doctor = make_doctor_user(specialization="Cardiology", branch="Central")
        client = APIClient()
        client.force_authenticate(doctor_user)

        response = client.patch(
            "/api/auth/me/", {"specialization": "Neurology", "branch": "North"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        doctor.refresh_from_db()
        self.assertEqual(doctor.specialization, "Cardiology")
        self.assertEqual(doctor.branch, "Central")

    def test_anonymous_cannot_access_me(self):
        response = APIClient().get("/api/auth/me/")

        self.assertEqual(response.status_code, 401)


class ChangePasswordTest(TestCase):
    def setUp(self):
        self.patient = make_patient(username="pw_patient")
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

    def test_change_password_with_correct_current_password(self):
        response = self.client.post(
            "/api/auth/change-password/",
            {"current_password": "TestPass123!", "new_password": "NewPass456!"},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.check_password("NewPass456!"))

    def test_change_password_with_wrong_current_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/change-password/",
            {"current_password": "WrongPass!", "new_password": "NewPass456!"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.patient.refresh_from_db()
        self.assertTrue(self.patient.check_password("TestPass123!"))

    def test_weak_new_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/change-password/",
            {"current_password": "TestPass123!", "new_password": "12345"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
