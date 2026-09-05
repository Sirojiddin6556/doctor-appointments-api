from django.utils import timezone
from rest_framework import serializers

from .models import Slot


class SlotSerializer(serializers.ModelSerializer):
    is_free = serializers.BooleanField(read_only=True)

    class Meta:
        model = Slot
        fields = ["id", "doctor", "start_time", "end_time", "is_free"]
        read_only_fields = ["id", "doctor", "is_free"]


class BookedBySerializer(serializers.Serializer):
    appointment_id = serializers.IntegerField()
    patient_username = serializers.CharField()
    status = serializers.CharField()


class DoctorScheduleSlotSerializer(serializers.ModelSerializer):
    """Used by GET /api/slots/mine/ — shows who (if anyone) booked each slot."""

    booked_by = serializers.SerializerMethodField()

    class Meta:
        model = Slot
        fields = ["id", "start_time", "end_time", "booked_by"]

    def get_booked_by(self, obj):
        appt = obj.active_appointment
        if appt is None:
            return None
        return {
            "appointment_id": appt.id,
            "patient_username": appt.patient.username,
            "status": appt.status,
        }


class SlotBulkCreateSerializer(serializers.Serializer):
    """
    POST /api/slots/ — create every slot for a working window in one request
    (the brief explicitly asks for "create a day's worth of slots in one
    request"). We accept the overall [start_time, end_time) window as full
    ISO 8601 datetimes (rule 8) plus a slot duration, and slice it into
    equal, back-to-back slots. All slots are created atomically: if any of
    them would overlap a slot the doctor already owns (rule 7, enforced by
    the DB ExclusionConstraint as the final authority), the whole batch is
    rejected rather than partially created.
    """

    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    slot_duration_minutes = serializers.IntegerField(min_value=5, max_value=8 * 60, default=30)

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError("end_time must be after start_time.")
        if attrs["start_time"] < timezone.now():
            raise serializers.ValidationError("Cannot create slots that start in the past.")
        return attrs

    def build_slot_windows(self):
        start = self.validated_data["start_time"]
        end = self.validated_data["end_time"]
        step = timezone.timedelta(minutes=self.validated_data["slot_duration_minutes"])

        windows = []
        cursor = start
        while cursor + step <= end:
            windows.append((cursor, cursor + step))
            cursor += step
        return windows
