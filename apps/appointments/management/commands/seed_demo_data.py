"""
Bonus: `python manage.py seed_demo_data` populates a fresh database with
enough data to poke at the API by hand (Swagger UI, curl, Postman) without
manually registering half a dozen accounts first.

Idempotent-ish: re-running it skips users that already exist by username
instead of erroring, so it's safe to run again after adding a migration.
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.doctors.models import Doctor
from apps.slots.models import Slot
from apps.users.models import User

DEMO_PASSWORD = "DemoPass123!"


class Command(BaseCommand):
    help = "Seed the database with demo doctors, patients, an admin, and a day of slots."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=1,
            help="How many days from now to generate the demo doctors' slots for (default: 1).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = []

        admin, was_created = self._get_or_create_user("admin_demo", role=User.Role.ADMIN, is_staff=True, is_superuser=True)
        if was_created:
            created.append(admin.username)

        doctors_spec = [
            ("dr_cardio", "Cardiology", "Central"),
            ("dr_neuro", "Neurology", "North"),
            ("dr_derma", "Dermatology", "Central"),
        ]
        doctors = []
        for username, specialization, branch in doctors_spec:
            user, was_created = self._get_or_create_user(username, role=User.Role.DOCTOR)
            if was_created:
                created.append(user.username)
            doctor, _ = Doctor.objects.get_or_create(
                user=user, defaults={"specialization": specialization, "branch": branch}
            )
            doctors.append(doctor)

        for i in range(1, 4):
            username = f"patient_demo{i}"
            user, was_created = self._get_or_create_user(username, role=User.Role.PATIENT)
            if was_created:
                created.append(user.username)

        day = timezone.now() + timedelta(days=options["days_ahead"])
        day_start = day.replace(hour=9, minute=0, second=0, microsecond=0)
        slots_created = 0
        for doctor in doctors:
            if Slot.objects.filter(doctor=doctor, start_time__date=day_start.date()).exists():
                continue
            cursor = day_start
            for _ in range(8):  # 09:00 - 13:00, 30 min each
                Slot.objects.create(doctor=doctor, start_time=cursor, end_time=cursor + timedelta(minutes=30))
                cursor += timedelta(minutes=30)
                slots_created += 1

        self.stdout.write(self.style.SUCCESS(f"Created {len(created)} new user(s): {', '.join(created) or '(none, already existed)'}"))
        self.stdout.write(self.style.SUCCESS(f"Created {slots_created} new slot(s) for {day_start.date()}."))
        self.stdout.write(self.style.SUCCESS(f"All demo accounts use the password: {DEMO_PASSWORD}"))
        self.stdout.write("Usernames: admin_demo, dr_cardio, dr_neuro, dr_derma, patient_demo1..3")

    @staticmethod
    def _get_or_create_user(username, **extra):
        user = User.objects.filter(username=username).first()
        if user:
            return user, False
        user = User.objects.create_user(username=username, password=DEMO_PASSWORD, **extra)
        return user, True
