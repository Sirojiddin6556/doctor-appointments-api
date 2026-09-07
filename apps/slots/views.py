from datetime import timezone as dt_timezone
import logging

from django.db import IntegrityError, transaction
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.permissions import IsDoctorRole, doctor_profile_or_403
from apps.doctors.models import DoctorWorkingHours

from .models import Slot
from .serializers import DoctorScheduleSlotSerializer, SlotBulkCreateSerializer, SlotSerializer

logger = logging.getLogger(__name__)


def _validate_against_working_hours(doctor_profile, windows):
    """Правило 9: слот можно создать только в рабочие часы врача, вне обеда.

    График обязателен: если для дня недели нет ни одной записи в
    DoctorWorkingHours, создание слота на этот день отклоняется — врач
    сначала задаёт график через PUT /api/doctors/me/working-hours/.
    """
    if not windows:
        return

    needed_weekdays = set()
    for start, end in windows:
        start_utc, end_utc = start.astimezone(dt_timezone.utc), end.astimezone(dt_timezone.utc)
        if start_utc.date() != end_utc.date():
            raise ValidationError(
                "A slot cannot span across midnight (UTC); split it into same-day slots."
            )
        needed_weekdays.add(start_utc.weekday())

    hours_by_weekday = {
        wh.weekday: wh
        for wh in DoctorWorkingHours.objects.filter(doctor=doctor_profile, weekday__in=needed_weekdays)
    }

    for start, end in windows:
        start_utc, end_utc = start.astimezone(dt_timezone.utc), end.astimezone(dt_timezone.utc)
        weekday = start_utc.weekday()
        weekday_label = DoctorWorkingHours.Weekday(weekday).label
        working_hours = hours_by_weekday.get(weekday)

        if working_hours is None:
            raise ValidationError(
                f"No working hours configured for {weekday_label}. "
                "Set your schedule first: PUT /api/doctors/me/working-hours/."
            )

        start_time, end_time = start_utc.time(), end_utc.time()
        if start_time < working_hours.start_time or end_time > working_hours.end_time:
            raise ValidationError(
                f"{weekday_label} working hours are {working_hours.start_time}–"
                f"{working_hours.end_time}; slot {start_time}–{end_time} is outside that window."
            )

        if (
            working_hours.break_start
            and start_time < working_hours.break_end
            and end_time > working_hours.break_start
        ):
            raise ValidationError(
                f"Slot {start_time}–{end_time} overlaps the lunch break "
                f"({working_hours.break_start}–{working_hours.break_end}) on {weekday_label}."
            )


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
        doctor_profile = doctor_profile_or_403(request.user)
        logger.info("Врач %s начал создание слотов", request.user.username)

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        windows = serializer.build_slot_windows()

        if not windows:
            raise ValidationError(
                "The given window is shorter than one slot_duration_minutes; no slots created."
            )

        _validate_against_working_hours(doctor_profile, windows)

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
        doctor_profile = doctor_profile_or_403(request.user)
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
