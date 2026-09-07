"""`/api/admin/users/` — правка и удаление пользователей администратором."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_admin, make_doctor_user, make_patient
from apps.slots.models import Slot


class AdminUserUpdateTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.patient = make_patient(username="target_patient", email="target@example.com")
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_can_update_patient(self):
        response = self.client.patch(
            f"/api/admin/users/{self.patient.id}/",
            {"first_name": "Пётр", "is_active": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.first_name, "Пётр")
        self.assertFalse(self.patient.is_active)

    def test_role_is_not_editable_through_this_endpoint(self):
        response = self.client.patch(
            f"/api/admin/users/{self.patient.id}/", {"role": "admin"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.role, "patient")

    def test_non_admin_cannot_update_users(self):
        other_patient = make_patient(username="other")
        client = APIClient()
        client.force_authenticate(other_patient)

        response = client.patch(
            f"/api/admin/users/{self.patient.id}/", {"first_name": "Hack"}, format="json"
        )

        self.assertEqual(response.status_code, 403)


class AdminUserDeleteTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_admin_can_delete_patient_without_history(self):
        patient = make_patient(username="deletable")

        response = self.client.delete(f"/api/admin/users/{patient.id}/")

        self.assertEqual(response.status_code, 204)

    def test_deleting_patient_with_appointment_is_rejected(self):
        patient = make_patient(username="has_history")
        _doctor_user, doctor = make_doctor_user()
        start = timezone.now() + timedelta(days=1)
        slot = Slot.objects.create(doctor=doctor, start_time=start, end_time=start + timedelta(minutes=30))
        Appointment.objects.create(
            slot=slot, patient=patient, start_time=slot.start_time, end_time=slot.end_time
        )

        response = self.client.delete(f"/api/admin/users/{patient.id}/")

        self.assertEqual(response.status_code, 400)
        patient.refresh_from_db()  # не должно бросить DoesNotExist

    def test_admin_cannot_delete_own_account(self):
        response = self.client.delete(f"/api/admin/users/{self.admin.id}/")

        self.assertEqual(response.status_code, 400)
