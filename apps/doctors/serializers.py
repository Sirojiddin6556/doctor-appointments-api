from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.users.models import User

from .models import Doctor, DoctorWorkingHours


class DoctorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = Doctor
        fields = ["id", "username", "full_name", "specialization", "branch"]

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username


class AdminDoctorSerializer(serializers.ModelSerializer):
    """Чтение карточки врача для админ-консоли."""

    user_id = serializers.IntegerField(source="user.id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    full_name = serializers.SerializerMethodField()
    email = serializers.EmailField(source="user.email", read_only=True)
    is_active = serializers.BooleanField(source="user.is_active", read_only=True)

    class Meta:
        model = Doctor
        fields = [
            "id", "user_id", "username", "full_name", "email",
            "specialization", "branch", "is_active",
        ]

    def get_full_name(self, obj) -> str:
        return obj.user.get_full_name() or obj.user.username


class AdminDoctorCreateSerializer(serializers.Serializer):
    """Создание учётной записи врача: пользователь + профиль одним запросом.

    Заменяет ручное заведение врача через Django admin / shell.
    """

    username = serializers.CharField(
        max_length=150,
        validators=[UniqueValidator(queryset=User.objects.all(), message="Username is already taken.")],
    )
    password = serializers.CharField(write_only=True, validators=[validate_password])
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all(), message="This email is already in use.")]
    )
    specialization = serializers.CharField(max_length=100)
    branch = serializers.CharField(max_length=100)

    @transaction.atomic
    def create(self, validated_data):
        user = User(
            username=validated_data["username"],
            email=validated_data["email"],
            first_name=validated_data["first_name"],
            last_name=validated_data["last_name"],
            role=User.Role.DOCTOR,
        )
        user.set_password(validated_data["password"])
        user.save()
        return Doctor.objects.create(
            user=user,
            specialization=validated_data["specialization"],
            branch=validated_data["branch"],
        )

    def to_representation(self, instance):
        return AdminDoctorSerializer(instance, context=self.context).data


class WorkingHoursDaySerializer(serializers.Serializer):
    """Один день недели для GET и PUT `/api/doctors/me/working-hours/`.

    На вход (PUT) день считается выходным, если его нет в списке вовсе —
    поэтому весь список заменяется целиком, частичного PATCH по одному дню нет.
    """

    weekday = serializers.ChoiceField(choices=DoctorWorkingHours.Weekday.choices)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    break_start = serializers.TimeField(required=False, allow_null=True, default=None)
    break_end = serializers.TimeField(required=False, allow_null=True, default=None)

    def validate(self, attrs):
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError("end_time must be after start_time.")
        break_start, break_end = attrs.get("break_start"), attrs.get("break_end")
        if bool(break_start) != bool(break_end):
            raise serializers.ValidationError(
                "break_start and break_end must be provided together (or both omitted)."
            )
        if break_start and break_end:
            if break_end <= break_start:
                raise serializers.ValidationError("break_end must be after break_start.")
            if break_start < attrs["start_time"] or break_end > attrs["end_time"]:
                raise serializers.ValidationError("The lunch break must fall within working hours.")
        return attrs


class WorkingHoursDayOutputSerializer(serializers.Serializer):
    """Форма одного дня в ответе GET/PUT `/api/doctors/me/working-hours/`."""

    weekday = serializers.IntegerField()
    weekday_label = serializers.CharField()
    is_working_day = serializers.BooleanField()
    start_time = serializers.TimeField(allow_null=True)
    end_time = serializers.TimeField(allow_null=True)
    break_start = serializers.TimeField(allow_null=True)
    break_end = serializers.TimeField(allow_null=True)


class AdminDoctorUpdateSerializer(serializers.Serializer):
    """Правка врача из админ-консоли: специализация, филиал, ФИО, активность."""

    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    specialization = serializers.CharField(max_length=100, required=False)
    branch = serializers.CharField(max_length=100, required=False)
    is_active = serializers.BooleanField(required=False)

    def update(self, instance, validated_data):
        user_fields = {}
        for field in ("first_name", "last_name", "is_active"):
            if field in validated_data:
                user_fields[field] = validated_data[field]
        if user_fields:
            for key, value in user_fields.items():
                setattr(instance.user, key, value)
            instance.user.save(update_fields=list(user_fields))
        for field in ("specialization", "branch"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        instance.save()
        return instance

    def to_representation(self, instance):
        return AdminDoctorSerializer(instance, context=self.context).data
