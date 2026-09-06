from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.appointments.models import Appointment
from apps.common.test_utils import make_doctor_user, make_patient
from apps.slots.models import Slot


class DoctorFilteringAndPaginationTest(TestCase):
    def setUp(self):
        _, self.cardio_central = make_doctor_user(
            username="d1", specialization="Cardiology", branch="Central"
        )
        _, self.neuro_north = make_doctor_user(
            username="d2", specialization="Neurology", branch="North"
        )
        _, self.cardio_north = make_doctor_user(
            username="d3", specialization="Cardiology", branch="North"
        )
        self.patient = make_patient()
        self.client = APIClient()
        self.client.force_authenticate(self.patient)

    def test_filter_by_specialization(self):
        response = self.client.get("/api/doctors/?specialization=Cardiology")

        usernames = {d["username"] for d in response.data["results"]}
        self.assertEqual(usernames, {"d1", "d3"})

    def test_filter_by_branch(self):
        response = self.client.get("/api/doctors/?branch=North")

        usernames = {d["username"] for d in response.data["results"]}
        self.assertEqual(usernames, {"d2", "d3"})

    def test_combined_filter(self):
        response = self.client.get("/api/doctors/?specialization=Cardiology&branch=North")

        usernames = {d["username"] for d in response.data["results"]}
        self.assertEqual(usernames, {"d3"})

    def test_list_is_paginated(self):
        response = self.client.get("/api/doctors/")

        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

    def test_search_matches_name_and_specialization(self):
        _, self.house = make_doctor_user(
            username="house", specialization="Diagnostics", branch="Central", last_name="House"
        )

        by_name = self.client.get("/api/doctors/?search=House")
        self.assertEqual({d["username"] for d in by_name.data["results"]}, {"house"})

        by_spec = self.client.get("/api/doctors/?search=cardio")
        self.assertEqual({d["username"] for d in by_spec.data["results"]}, {"d1", "d3"})

    def test_page_size_query_param_is_respected(self):
        response = self.client.get("/api/doctors/?page_size=1")

        self.assertEqual(len(response.data["results"]), 1)
        self.assertIsNotNone(response.data["next"])


class FreeSlotsEndpointTest(TestCase):
    def setUp(self):
        _, self.doctor = make_doctor_user()
        self.patient = make_patient()
        self.client = APIClient()
        self.client.force_authenticate(self.patient)
        self.date = (timezone.now() + timedelta(days=1)).date()

    def test_booked_slot_excluded_from_free_list(self):
        day_start = timezone.now().replace(hour=9, minute=0, second=0, microsecond=0) + timedelta(days=1)
        free_slot = Slot.objects.create(doctor=self.doctor, start_time=day_start, end_time=day_start + timedelta(minutes=30))
        booked_slot_time = day_start + timedelta(hours=1)
        booked_slot = Slot.objects.create(
            doctor=self.doctor, start_time=booked_slot_time, end_time=booked_slot_time + timedelta(minutes=30)
        )
        Appointment.objects.create(
            slot=booked_slot, patient=self.patient,
            start_time=booked_slot.start_time, end_time=booked_slot.end_time,
            status=Appointment.Status.BOOKED,
        )

        response = self.client.get(f"/api/doctors/{self.doctor.id}/slots/?date={self.date}")

        returned_ids = [s["id"] for s in response.data]
        self.assertIn(free_slot.id, returned_ids)
        self.assertNotIn(booked_slot.id, returned_ids)

    def test_missing_date_param_returns_400(self):
        response = self.client.get(f"/api/doctors/{self.doctor.id}/slots/")

        self.assertEqual(response.status_code, 400)

    def test_invalid_date_param_returns_400(self):
        response = self.client.get(f"/api/doctors/{self.doctor.id}/slots/?date=not-a-date")

        self.assertEqual(response.status_code, 400)
