from datetime import datetime
from datetime import timezone as dt_timezone
import logging

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsDoctorRole, doctor_profile_or_403
from apps.slots.models import Slot
from apps.slots.serializers import SlotSerializer

from .filters import DoctorFilter
from .models import Doctor, DoctorWorkingHours
from .serializers import DoctorSerializer, WorkingHoursDayOutputSerializer, WorkingHoursDaySerializer

logger = logging.getLogger(__name__)


class DoctorViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Список врачей и свободных слотов выбранного врача."""

    queryset = Doctor.objects.select_related("user").all()
    serializer_class = DoctorSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = DoctorFilter
    # Свободный поиск ?search= по имени/фамилии/логину и специализации.
    search_fields = [
        "specialization",
        "user__first_name",
        "user__last_name",
        "user__username",
    ]

    @action(detail=True, methods=["get"], url_path="slots")
    def slots(self, request, pk=None):
        doctor = self.get_object()
        date_str = request.query_params.get("date")
        logger.info("Запрошены свободные слоты врача %s за дату %s", doctor.id, date_str)
        if not date_str:
            return Response(
                {"detail": "Query parameter 'date' is required, format YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        date = parse_date(date_str)
        if date is None:
            return Response(
                {"detail": "Invalid 'date'. Expected format: YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # `date` трактуется как календарные сутки в UTC (см. README, «Допущения»).
        day_start = timezone.make_aware(datetime.combine(date, datetime.min.time()), dt_timezone.utc)
        day_end = timezone.make_aware(datetime.combine(date, datetime.max.time()), dt_timezone.utc)
        # Нижняя граница — не раньше «сейчас»: уже прошедшие слоты сегодняшнего
        # дня забронировать нельзя (правило 2), поэтому и в выдаче их нет.
        lower_bound = max(day_start, timezone.now())

        free_slots = (
            Slot.objects.filter(doctor=doctor, start_time__gt=lower_bound, start_time__lte=day_end)
            .exclude(appointments__status="booked")
            .order_by("start_time")
        )
        serializer = SlotSerializer(free_slots, many=True)
        logger.info("Список свободных слотов врача %s сформирован", doctor.id)
        return Response(serializer.data)


class DoctorWorkingHoursView(APIView):
    """
    GET /api/doctors/me/working-hours/ -- собственный график, все 7 дней недели
    PUT /api/doctors/me/working-hours/ -- заменить график целиком (выходные — не перечислять)
    """

    permission_classes = [IsDoctorRole]

    def _serialize_week(self, doctor_profile):
        by_weekday = {wh.weekday: wh for wh in DoctorWorkingHours.objects.filter(doctor=doctor_profile)}
        week = []
        for weekday, label in DoctorWorkingHours.Weekday.choices:
            working_hours = by_weekday.get(weekday)
            week.append(
                {
                    "weekday": weekday,
                    "weekday_label": label,
                    "is_working_day": working_hours is not None,
                    "start_time": working_hours.start_time if working_hours else None,
                    "end_time": working_hours.end_time if working_hours else None,
                    "break_start": working_hours.break_start if working_hours else None,
                    "break_end": working_hours.break_end if working_hours else None,
                }
            )
        return week

    @extend_schema(responses=WorkingHoursDayOutputSerializer(many=True))
    def get(self, request):
        doctor_profile = doctor_profile_or_403(request.user)
        return Response(self._serialize_week(doctor_profile))

    @extend_schema(
        request=WorkingHoursDaySerializer(many=True),
        responses=WorkingHoursDayOutputSerializer(many=True),
    )
    def put(self, request):
        doctor_profile = doctor_profile_or_403(request.user)
        serializer = WorkingHoursDaySerializer(data=request.data, many=True)
        serializer.is_valid(raise_exception=True)
        days = serializer.validated_data

        weekdays = [int(day["weekday"]) for day in days]
        if len(weekdays) != len(set(weekdays)):
            raise ValidationError("Each weekday can only appear once in the schedule.")

        with transaction.atomic():
            DoctorWorkingHours.objects.filter(doctor=doctor_profile).delete()
            DoctorWorkingHours.objects.bulk_create(
                [
                    DoctorWorkingHours(
                        doctor=doctor_profile,
                        weekday=day["weekday"],
                        start_time=day["start_time"],
                        end_time=day["end_time"],
                        break_start=day.get("break_start"),
                        break_end=day.get("break_end"),
                    )
                    for day in days
                ]
            )
        logger.info("Врач %s обновил рабочий график (%s дн.)", request.user.username, len(days))
        return Response(self._serialize_week(doctor_profile))
