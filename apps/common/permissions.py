"""
Shared DRF permission classes.

Rule 6 explicitly requires that ownership/role checks happen on the API side,
not the frontend. Two layers are used together everywhere they matter:

1. A role check (IsPatientRole / IsDoctorRole / IsAdminRole) — is this user
   even allowed to call this endpoint at all.
2. A queryset filter in the view's get_queryset() (see each app's views.py)
   PLUS an object-level permission below — even if someone guesses another
   user's object id, has_object_permission stops them from touching it.

Both layers are kept because a queryset filter alone protects list/retrieve,
but a mistake in an update/delete view that forgets to filter the queryset
would still be safe if has_object_permission also runs.
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
    """Object-level check: the appointment belongs to the requesting patient."""

    message = "You can only access your own appointments."

    def has_object_permission(self, request, view, obj):
        return obj.patient_id == request.user.id


class IsOwnerDoctor(BasePermission):
    """Object-level check: the slot belongs to the requesting doctor's profile."""

    message = "You can only access your own slots."

    def has_object_permission(self, request, view, obj):
        doctor_profile = getattr(request.user, "doctor_profile", None)
        return doctor_profile is not None and obj.doctor_id == doctor_profile.id
