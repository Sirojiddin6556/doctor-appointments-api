"""Админ-консоль: управление учётными записями врачей.

Даёт админу через API то, что раньше делалось только в Django admin:
создать врача (пользователь + профиль), поправить специализацию/филиал/ФИО,
временно отключить или удалить.
"""

import logging

from django.db.models import ProtectedError
from rest_framework import filters, mixins, status, viewsets
from rest_framework.response import Response

from apps.common.permissions import IsAdminRole

from .models import Doctor
from .serializers import (
    AdminDoctorCreateSerializer,
    AdminDoctorSerializer,
    AdminDoctorUpdateSerializer,
)

logger = logging.getLogger(__name__)


class AdminDoctorViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsAdminRole]
    queryset = Doctor.objects.select_related("user").order_by("id")
    filter_backends = [filters.SearchFilter]
    search_fields = ["specialization", "branch", "user__username", "user__first_name", "user__last_name"]

    def get_serializer_class(self):
        if self.action == "create":
            return AdminDoctorCreateSerializer
        if self.action in ("update", "partial_update"):
            return AdminDoctorUpdateSerializer
        return AdminDoctorSerializer

    def perform_create(self, serializer):
        doctor = serializer.save()
        logger.info("Админ %s создал врача %s", self.request.user.username, doctor.user.username)

    def destroy(self, request, *args, **kwargs):
        doctor = self.get_object()
        username = doctor.user.username
        try:
            # User.delete() каскадит на Doctor и его Slot; Appointment.slot стоит
            # на PROTECT, поэтому у врача с записями удаление будет отклонено.
            doctor.user.delete()
        except ProtectedError:
            return Response(
                {"detail": "Нельзя удалить врача: на его слотах есть записи. Отключите учётную запись (is_active=false)."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info("Админ %s удалил врача %s", request.user.username, username)
        return Response(status=status.HTTP_204_NO_CONTENT)
