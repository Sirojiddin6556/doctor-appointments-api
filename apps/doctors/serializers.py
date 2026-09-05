from rest_framework import serializers

from .models import Doctor


class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Doctor
        fields = ["id", "username", "full_name", "specialization", "branch"]

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username
