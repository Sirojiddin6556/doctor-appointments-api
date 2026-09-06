from rest_framework import serializers

from .models import Appointment


class AppointmentCreateSerializer(serializers.Serializer):
    slot = serializers.IntegerField()


class AppointmentSerializer(serializers.ModelSerializer):
    doctor_name = serializers.SerializerMethodField()
    specialization = serializers.CharField(source="slot.doctor.specialization", read_only=True)
    branch = serializers.CharField(source="slot.doctor.branch", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "slot",
            "doctor_name",
            "specialization",
            "branch",
            "start_time",
            "end_time",
            "status",
            "created_at",
            "cancelled_at",
        ]
        read_only_fields = fields

    def get_doctor_name(self, obj) -> str:
        doctor_user = obj.slot.doctor.user
        return doctor_user.get_full_name() or doctor_user.username


class AdminAppointmentSerializer(serializers.ModelSerializer):
    patient_username = serializers.CharField(source="patient.username", read_only=True)
    doctor_username = serializers.CharField(source="slot.doctor.user.username", read_only=True)
    specialization = serializers.CharField(source="slot.doctor.specialization", read_only=True)
    branch = serializers.CharField(source="slot.doctor.branch", read_only=True)

    class Meta:
        model = Appointment
        fields = [
            "id",
            "patient_username",
            "doctor_username",
            "specialization",
            "branch",
            "start_time",
            "end_time",
            "status",
            "created_at",
            "cancelled_at",
        ]
        read_only_fields = fields
