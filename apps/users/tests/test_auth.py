from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.test_utils import make_patient
from apps.users.models import User


class RegistrationTest(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_patient_can_self_register(self):
        response = self.client.post(
            "/api/auth/register/",
            {"username": "newpatient", "password": "StrongPass123!", "email": "np@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="newpatient")
        self.assertEqual(user.role, User.Role.PATIENT)
        self.assertTrue(user.check_password("StrongPass123!"))
        # Пароль нельзя хранить или возвращать в открытом виде.
        self.assertNotIn("password", response.data)

    def test_registration_cannot_grant_doctor_or_admin_role(self):
        """
        Even if a caller stuffs an extra "role" field into the payload, the
        serializer must ignore it -- self-registration always yields a
        patient. Anything else would let anyone declare themselves a
        doctor or admin.
        """
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "sneaky",
                "password": "StrongPass123!",
                "email": "sneaky@test.com",
                "role": "admin",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="sneaky")
        self.assertEqual(user.role, User.Role.PATIENT)

    def test_duplicate_username_is_rejected(self):
        make_patient(username="taken")

        response = self.client.post(
            "/api/auth/register/",
            {"username": "taken", "password": "StrongPass123!", "email": "taken@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_registration_requires_email(self):
        response = self.client.post(
            "/api/auth/register/",
            {"username": "noemail", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)

    def test_duplicate_email_is_rejected(self):
        self.client.post(
            "/api/auth/register/",
            {"username": "first", "password": "StrongPass123!", "email": "dup@test.com"},
            format="json",
        )

        response = self.client.post(
            "/api/auth/register/",
            {"username": "second", "password": "StrongPass123!", "email": "dup@test.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("email", response.data)


class LoginTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.patient = make_patient(username="loginuser")

    def test_login_returns_access_and_refresh_tokens(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "loginuser", "password": "TestPass123!"}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["role"], "patient")

    def test_login_with_wrong_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/login/", {"username": "loginuser", "password": "WrongPassword"}, format="json"
        )

        self.assertEqual(response.status_code, 401)

    def test_refresh_token_returns_new_access_token(self):
        login = self.client.post(
            "/api/auth/login/", {"username": "loginuser", "password": "TestPass123!"}, format="json"
        )
        refresh_token = login.data["refresh"]

        response = self.client.post("/api/auth/refresh/", {"refresh": refresh_token}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)

    def test_logout_blacklists_refresh_token(self):
        login = self.client.post(
            "/api/auth/login/", {"username": "loginuser", "password": "TestPass123!"}, format="json"
        )
        access, refresh = login.data["access"], login.data["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        logout = self.client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
        self.assertEqual(logout.status_code, 205)

        # Отозванный refresh больше не годится для обновления access.
        self.client.credentials()
        reuse = self.client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
        self.assertEqual(reuse.status_code, 401)
