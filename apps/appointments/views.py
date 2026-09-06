import logging

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

# Имена ограничений хранятся в одном месте для view и тестов.
UNIQUE_ACTIVE_BOOKING_PER_SLOT = "unique_active_booking_per_slot"
APPOINTMENT_NO_OVERLAP_PER_PATIENT = "appointment_no_overlap_per_patient"

logger = logging.getLogger(__name__)


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
    """Создание, просмотр и отмена записей пациента."""

    permission_classes = [IsPatientRole]

    def get_queryset(self):
        # Правило 6: пациент видит только собственные записи.
        qs = (
            Appointment.objects.filter(patient=self.request.user)
            .select_related("slot__doctor__user")
            .order_by("-created_at")
        )
        # Необязательный фильтр ?status=booked|cancelled|completed
        # (можно перечислить через запятую). Без него возвращается вся история.
        status_param = self.request.query_params.get("status")
        if status_param:
            wanted = {s.strip() for s in status_param.split(",") if s.strip()}
            valid = set(Appointment.Status.values)
            qs = qs.filter(status__in=(wanted & valid) or {"__none__"})
        return qs

    def get_serializer_class(self):
        if self.action == "create":
            return AppointmentCreateSerializer
        return AppointmentSerializer

    def create(self, request, *args, **kwargs):
        logger.info("Начато бронирование слота пользователем %s", request.user.username)
        input_serializer = self.get_serializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        slot_id = input_serializer.validated_data["slot"]

        try:
            with transaction.atomic():
                # Блокировка строки последовательно обрабатывает параллельные
                # попытки бронирования одного слота.
                try:
                    slot = Slot.objects.select_for_update().select_related("doctor").get(pk=slot_id)
                except Slot.DoesNotExist:
                    raise ValidationError({"slot": "Slot not found."})

                # Правило 2: нельзя бронировать начавшийся или прошедший слот.
                if slot.start_time <= timezone.now():
                    raise ValidationError({"slot": "This slot is in the past and cannot be booked."})

                # Правило 1: прикладная проверка дополняет ограничение БД.
                if not slot.is_free:
                    raise ValidationError({"slot": "This slot is already booked."})

                # Правило 3: прикладная проверка дополняет ограничение БД
                # от пересечений записей пациента.
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
            # Ограничения БД остаются защитой даже при гонке запросов.
            logger.warning("Бронирование отклонено ограничением базы данных: %s", exc)
            raise ValidationError({"slot": _friendly_integrity_error_message(exc)})

        logger.info("Слот %s забронирован пользователем %s", slot_id, request.user.username)
        return Response(AppointmentSerializer(appointment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="cancel", permission_classes=[IsPatientRole, IsOwnerPatient])
    def cancel(self, request, pk=None):
        appointment = self.get_object()
        logger.info("Запрошена отмена записи %s пользователем %s", pk, request.user.username)

        if appointment.status != Appointment.Status.BOOKED:
            raise ValidationError({"detail": f"Appointment is already '{appointment.status}'."})

        # Правило 4: отмена разрешена только более чем за 2 часа до начала.
        if not appointment.can_be_cancelled:
            raise ValidationError(
                {"detail": "Appointments can only be cancelled more than 2 hours before the slot starts."}
            )

        appointment.status = Appointment.Status.CANCELLED
        appointment.cancelled_at = timezone.now()
        appointment.save(update_fields=["status", "cancelled_at"])
        # Правило 5: свободность слота вычисляется по отсутствию активной записи.
        logger.info("Запись %s отменена пользователем %s", pk, request.user.username)
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
    """Список всех записей для администратора с фильтрами и принудительной отменой."""

    permission_classes = [IsAdminRole]
    serializer_class = AdminAppointmentSerializer
    filterset_class = AdminAppointmentFilter
    queryset = (
        Appointment.objects.select_related("patient", "slot__doctor__user")
        .all()
        .order_by("-start_time")
    )

    def list(self, request, *args, **kwargs):
        logger.info("Администратор %s запросил список записей", request.user.username)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="cancel")
    def cancel(self, request, pk=None):
        """Административная отмена: без ограничения «за 2 часа» (правило 4 —
        для пациента). Слот освобождается (правило 5)."""
        appointment = self.get_object()
        if appointment.status != Appointment.Status.BOOKED:
            raise ValidationError({"detail": f"Appointment is already '{appointment.status}'."})
        appointment.status = Appointment.Status.CANCELLED
        appointment.cancelled_at = timezone.now()
        appointment.save(update_fields=["status", "cancelled_at"])
        logger.info("Админ %s отменил запись %s", request.user.username, pk)
        return Response(AdminAppointmentSerializer(appointment).data)
