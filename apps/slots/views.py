import logging

from django.db import IntegrityError, transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.common.permissions import IsDoctorRole

from .models import Slot
from .serializers import DoctorScheduleSlotSerializer, SlotBulkCreateSerializer, SlotSerializer

logger = logging.getLogger(__name__)


def _doctor_profile_or_403(user):
    doctor_profile = getattr(user, "doctor_profile", None)
    if doctor_profile is None:
        raise PermissionDenied(
            "Your account has role=doctor but no Doctor profile. Ask an admin to create one."
        )
    return doctor_profile


class SlotViewSet(viewsets.GenericViewSet, mixins.CreateModelMixin):
    """
    POST /api/slots/       -- doctor creates a batch of slots for themselves
    GET  /api/slots/mine/  -- doctor's own schedule, with who booked each slot
    """

    permission_classes = [IsDoctorRole]
    queryset = Slot.objects.all()

    def get_serializer_class(self):
        if self.action == "mine":
            return DoctorScheduleSlotSerializer
        return SlotBulkCreateSerializer

    def create(self, request, *args, **kwargs):
        doctor_profile = _doctor_profile_or_403(request.user)
        logger.info("Врач %s начал создание слотов", request.user.username)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        windows = serializer.build_slot_windows()

        if not windows:
            raise ValidationError(
                "The given window is shorter than one slot_duration_minutes; no slots created."
            )

        try:
            with transaction.atomic():
                created = [
                    Slot.objects.create(doctor=doctor_profile, start_time=s, end_time=e)
                    for s, e in windows
                ]
        except IntegrityError:
            # Правило 7: ограничение БД отклонило пересекающийся слот.
            logger.warning("Врач %s попытался создать пересекающиеся слоты", request.user.username)
            raise ValidationError(
                "Could not create the requested slots: one or more of them overlaps "
                "a slot you already have. No slots were created (all-or-nothing)."
            )

        logger.info("Врач %s создал %s слотов", request.user.username, len(created))
        return Response(SlotSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        doctor_profile = _doctor_profile_or_403(request.user)
        logger.info("Врач %s запросил собственное расписание", request.user.username)
        slots = (
            Slot.objects.filter(doctor=doctor_profile)
            .select_related("doctor")
            .prefetch_related("appointments__patient")
            .order_by("start_time")
        )
        page = self.paginate_queryset(slots)
        serializer = DoctorScheduleSlotSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)
