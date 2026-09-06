from datetime import datetime
from datetime import timezone as dt_timezone
import logging

from django.utils import timezone
from django.utils.dateparse import parse_date
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.slots.models import Slot
from apps.slots.serializers import SlotSerializer

from .filters import DoctorFilter
from .models import Doctor
from .serializers import DoctorSerializer

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
