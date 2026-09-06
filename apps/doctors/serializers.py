from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from apps.users.models import User

from .models import Doctor


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
