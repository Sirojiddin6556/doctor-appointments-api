"""Общие классы разрешений DRF.

Правило 6 требует проверять роль и владельца на стороне API. Поэтому
используются два уровня защиты: роль пользователя и фильтрация объектов
вместе с объектным разрешением.
"""

from rest_framework.permissions import BasePermission

from apps.users.models import User


class IsPatientRole(BasePermission):
    message = "This action is only available to patients."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.PATIENT)


class IsDoctorRole(BasePermission):
    message = "This action is only available to doctors."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.DOCTOR)


class IsAdminRole(BasePermission):
    message = "This action is only available to administrators."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == User.Role.ADMIN)


class IsOwnerPatient(BasePermission):
    """Проверка, что запись принадлежит текущему пациенту."""

    message = "You can only access your own appointments."

    def has_object_permission(self, request, view, obj):
        return obj.patient_id == request.user.id


class IsOwnerDoctor(BasePermission):
    """Проверка, что слот принадлежит профилю текущего врача."""

    message = "You can only access your own slots."

    def has_object_permission(self, request, view, obj):
        doctor_profile = getattr(request.user, "doctor_profile", None)
        return doctor_profile is not None and obj.doctor_id == doctor_profile.id
