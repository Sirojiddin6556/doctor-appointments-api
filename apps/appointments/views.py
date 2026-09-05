from django.db import IntegrityError, transaction
from django.utils import timezone
from django_filters import rest_framework as django_filters
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from apps.common.permissions import IsAdminRole, IsOwnerPatient, IsPatientRole
from apps.slots.models import Slot

from .models import Appointment
from .serializers import AdminAppointmentSerializer, AppointmentCreateSerializer, AppointmentSerializer

# Constraint names, kept in one place so the view and its tests agree on them.
UNIQUE_ACTIVE_BOOKING_PER_SLOT = "unique_active_booking_per_slot"
APPOINTMENT_NO_OVERLAP_PER_PATIENT = "appointment_no_overlap_per_patient"


def _friendly_integrity_error_message(exc: IntegrityError) -> str:
    diag = getattr(getattr(exc, "__cause__", None), "diag", None)
    constraint_name = getattr(diag, "constraint_name", "") or ""
    if UNIQUE_ACTIVE_BOOKING_PER_SLOT in constraint_name:
        return "This slot has just been booked by someone else. Please choose another slot."
    if APPOINTMENT_NO_OVERLAP_PER_PATIENT in constraint_name:
        return "You already have a booked appointment that overlaps this time."
    return "Could not complete the booking due to a conflicting appointment."


class AppointmentViewSet(
    mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet
):
    """
    POST /api/appointments/            -- book a slot
    GET  /api/appointments/            -- only the caller's own appointments
    POST /api/appointments/{id}/cancel/
    """

    permission_classes = [IsPatientRole]

    def get_queryset(self):
        # Rule 6: a patient only ever sees their own appointments.
        return (
            Appointment.objects.filter(patient=self.request.user)
            .select_related("slot__doctor__user")
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return AppointmentCreateSerializer
        return AppointmentSerializer

    def create(self, request, *args, **kwargs):
        input_serializer = self.get_serializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        slot_id = input_serializer.validated_data["slot"]

        try:
            with transaction.atomic():
                # Row-level lock: serializes concurrent booking attempts for
                # THIS slot. This is what turns "two requests arrive at the
                # same instant" into "one waits its turn" instead of a race
                # (rule 1). The second request only proceeds once the first
                # has committed (or rolled back), by which point is_free
                # correctly reflects reality.
                try:
                    slot = Slot.objects.select_for_update().select_related("doctor").get(pk=slot_id)
                except Slot.DoesNotExist:
                    raise ValidationError({"slot": "Slot not found."})

                # Rule 2: no booking a slot that has already started/passed.
                if slot.start_time <= timezone.now():
                    raise ValidationError({"slot": "This slot is in the past and cannot be booked."})

                # Rule 1 (application-level half; the DB partial unique
                # constraint below is the actual guarantee).
                if not slot.is_free:
                    raise ValidationError({"slot": "This slot is already booked."})

                # Rule 3 (application-level half; the DB exclusion
                # constraint below is the actual guarantee against races
                # across two *different* slots booked at the same instant).
                overlapping = Appointment.objects.filter(
                    patient=request.user,
                    status=Appointment.Status.BOOKED,
                    start_time__lt=slot.end_time,
                    end_time__gt=slot.start_time,
                ).exists()
                if overlapping:
                    raise ValidationError(
                        {"slot": "You already have a booked appointment overlapping this time."}
                    )

                appointment = Appointment.objects.create(
                    slot=slot,
                    patient=request.user,
                    start_time=slot.start_time,
                    end_time=slot.end_time,
                    status=Appointment.Status.BOOKED,
                )
        except IntegrityError as exc:
            # Defense in depth: if two requests somehow both got past the
            # application checks above (e.g. a future code change removes
            # the lock), the database constraints still guarantee only one
            # booking wins. We surface that as a clean 400, never a 500.
            raise ValidationError({"slot": _friendly_integrity_error_message(exc)})

        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cancel", permission_classes=[IsPatientRole, IsOwnerPatient])
    def cancel(self, request, pk=None):
        appointment = self.get_object()

        if appointment.status != Appointment.Status.BOOKED:
            raise ValidationError({"detail": f"Appointment is already '{appointment.status}'."})

        # Rule 4: cancellation only allowed while more than 2 hours remain.
        if not appointment.can_be_cancelled:
            raise ValidationError(
                {"detail": "Appointments can only be cancelled more than 2 hours before the slot starts."}
            )

        appointment.status = Appointment.Status.CANCELLED
        appointment.cancelled_at = timezone.now()
        appointment.save(update_fields=["status", "cancelled_at"])
        # Rule 5: nothing else to do — a slot's "free" state is derived from
        # the absence of a booked Appointment, so it is immediately
        # re-bookable by anyone.
        return Response(AppointmentSerializer(appointment).data)


class AdminAppointmentFilter(django_filters.FilterSet):
    doctor = django_filters.NumberFilter(field_name="slot__doctor_id")
    branch = django_filters.CharFilter(field_name="slot__doctor__branch", lookup_expr="iexact")
    date_from = django_filters.DateFilter(method="filter_date_from")
    date_to = django_filters.DateFilter(method="filter_date_to")

    class Meta:
        model = Appointment
        fields = ["doctor", "branch", "status"]

    def filter_date_from(self, queryset, name, value):
        return queryset.filter(start_time__date__gte=value)

    def filter_date_to(self, queryset, name, value):
        return queryset.filter(start_time__date__lte=value)


class AdminAppointmentViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """GET /api/admin/appointments/ -- all appointments; filter by doctor/branch/date range."""

    permission_classes = [IsAdminRole]
    serializer_class = AdminAppointmentSerializer
    filterset_class = AdminAppointmentFilter
    queryset = (
        Appointment.objects.select_related("patient", "slot__doctor__user")
        .all()
        .order_by("-start_time")
    )
