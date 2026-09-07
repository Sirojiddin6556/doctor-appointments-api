"""Общие помощники для подготовки тестовых данных приложений."""

from datetime import time

from apps.doctors.models import Doctor, DoctorWorkingHours
from apps.users.models import User


def make_patient(username="patient", **kwargs):
    return User.objects.create_user(username=username, password="TestPass123!", role=User.Role.PATIENT, **kwargs)


def make_doctor_user(
    username="doctor", specialization="Cardiology", branch="Central", with_working_hours=True, **kwargs
):
    """Создать врача с профилем.

    По умолчанию сразу выдаёт разрешительный график на все 7 дней недели
    (00:00-23:59, без обеда), чтобы правило 9 (график обязателен для создания
    слотов) не мешало тестам, которые проверяют что-то другое. Передайте
    `with_working_hours=False`, если тест как раз проверяет само правило 9.
    """
    user = User.objects.create_user(username=username, password="TestPass123!", role=User.Role.DOCTOR, **kwargs)
    doctor = Doctor.objects.create(user=user, specialization=specialization, branch=branch)
    if with_working_hours:
        DoctorWorkingHours.objects.bulk_create(
            [
                DoctorWorkingHours(doctor=doctor, weekday=weekday, start_time=time(0, 0), end_time=time(23, 59))
                for weekday, _ in DoctorWorkingHours.Weekday.choices
            ]
        )
    return user, doctor


def make_admin(username="admin", **kwargs):
    return User.objects.create_user(username=username, password="TestPass123!", role=User.Role.ADMIN, **kwargs)
