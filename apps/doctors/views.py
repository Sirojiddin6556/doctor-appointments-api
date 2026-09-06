from datetime import datetime, timezone as dt_timezone

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.slots.models import Slot
from apps.slots.serializers import SlotSerializer

from .filters import DoctorFilter
from .models import Doctor
from .serializers import DoctorSerializer


class DoctorViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET /api/doctors/                    -- list, filter by specialization/branch, paginated
    GET /api/doctors/{id}/slots/?date=   -- that doctor's FREE slots on a given UTC date
    """

    queryset = Doctor.objects.select_related("user").all()
    serializer_class = DoctorSerializer
    filterset_class = DoctorFilter

    @action(detail=True, methods=["get"], url_path="slots")
    def slots(self, request, pk=None):
        doctor = self.get_object()
        date_str = request.query_params.get("date")
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

        day_start = timezone.make_aware(datetime.combine(date, datetime.min.time()), dt_timezone.utc)
        day_end = timezone.make_aware(datetime.combine(date, datetime.max.time()), dt_timezone.utc)

        free_slots = (
            Slot.objects.filter(doctor=doctor, start_time__gte=day_start, start_time__lte=day_end)
            .exclude(appointments__status="booked")
            .order_by("start_time")
        )
        serializer = SlotSerializer(free_slots, many=True)
        return Response(serializer.data)
