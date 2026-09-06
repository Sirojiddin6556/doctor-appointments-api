"""Админ-консоль: создание и правка учётных записей врачей через API."""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.test_utils import make_admin, make_doctor_user, make_patient
from apps.doctors.models import Doctor
from apps.users.models import User


class AdminDoctorCrudTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _create_payload(self, **overrides):
        payload = {
            "username": "new_doc",
            "password": "DoctorPass123!",
            "first_name": "Ada",
            "last_name": "Lovelace",
            "email": "ada@clinic.test",
            "specialization": "Genetics",
            "branch": "West",
        }
        payload.update(overrides)
        return payload

    def test_admin_creates_doctor_account_and_profile(self):
        response = self.client.post("/api/admin/doctors/", self._create_payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="new_doc")
        self.assertEqual(user.role, User.Role.DOCTOR)
        self.assertTrue(user.check_password("DoctorPass123!"))
        self.assertTrue(Doctor.objects.filter(user=user, specialization="Genetics").exists())

    def test_created_doctor_can_use_doctor_endpoints(self):
        self.client.post("/api/admin/doctors/", self._create_payload(), format="json")

        doctor_client = APIClient()
        login = doctor_client.post(
            "/api/auth/login/", {"username": "new_doc", "password": "DoctorPass123!"}, format="json"
        )
        doctor_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        schedule = doctor_client.get("/api/slots/mine/")
        self.assertEqual(schedule.status_code, 200)

    def test_patch_updates_specialization_and_branch(self):
        create = self.client.post("/api/admin/doctors/", self._create_payload(), format="json")
        doctor_id = create.data["id"]

        response = self.client.patch(
            f"/api/admin/doctors/{doctor_id}/",
            {"specialization": "Cardiology", "branch": "Central", "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        doctor = Doctor.objects.select_related("user").get(pk=doctor_id)
        self.assertEqual(doctor.specialization, "Cardiology")
        self.assertFalse(doctor.user.is_active)

    def test_duplicate_username_or_email_rejected(self):
        self.client.post("/api/admin/doctors/", self._create_payload(), format="json")

        dup_username = self.client.post(
            "/api/admin/doctors/", self._create_payload(email="other@clinic.test"), format="json"
        )
        dup_email = self.client.post(
            "/api/admin/doctors/", self._create_payload(username="other_doc"), format="json"
        )

        self.assertEqual(dup_username.status_code, 400)
        self.assertEqual(dup_email.status_code, 400)

    def test_delete_removes_doctor_and_user(self):
        create = self.client.post("/api/admin/doctors/", self._create_payload(), format="json")
        doctor_id = create.data["id"]

        response = self.client.delete(f"/api/admin/doctors/{doctor_id}/")

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Doctor.objects.filter(pk=doctor_id).exists())
        self.assertFalse(User.objects.filter(username="new_doc").exists())

    def test_non_admin_is_forbidden(self):
        for user in (make_patient(username="p_forbidden"), make_doctor_user(username="d_forbidden")[0]):
            client = APIClient()
            client.force_authenticate(user)
            self.assertEqual(client.get("/api/admin/doctors/").status_code, 403)
            self.assertEqual(
                client.post("/api/admin/doctors/", self._create_payload(), format="json").status_code,
                403,
            )


class AdminUserListTest(TestCase):
    def test_admin_lists_and_filters_users(self):
        admin = make_admin()
        make_doctor_user(username="list_doc")
        make_patient(username="list_pat")
        client = APIClient()
        client.force_authenticate(admin)

        everyone = client.get("/api/admin/users/")
        self.assertEqual(everyone.status_code, 200)
        self.assertGreaterEqual(everyone.data["count"], 3)

        doctors_only = client.get("/api/admin/users/?role=doctor")
        self.assertTrue(all(u["role"] == "doctor" for u in doctors_only.data["results"]))

    def test_non_admin_forbidden(self):
        client = APIClient()
        client.force_authenticate(make_patient(username="p_users"))
        self.assertEqual(client.get("/api/admin/users/").status_code, 403)
