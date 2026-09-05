"""Общие помощники для подготовки тестовых данных приложений."""

from apps.doctors.models import Doctor
from apps.users.models import User


def make_patient(username="patient", **kwargs):
    return User.objects.create_user(username=username, password="TestPass123!", role=User.Role.PATIENT, **kwargs)


def make_doctor_user(username="doctor", specialization="Cardiology", branch="Central", **kwargs):
    user = User.objects.create_user(username=username, password="TestPass123!", role=User.Role.DOCTOR, **kwargs)
    doctor = Doctor.objects.create(user=user, specialization=specialization, branch=branch)
    return user, doctor


def make_admin(username="admin", **kwargs):
    return User.objects.create_user(username=username, password="TestPass123!", role=User.Role.ADMIN, **kwargs)
