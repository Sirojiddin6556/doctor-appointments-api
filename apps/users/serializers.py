from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class PatientRegisterSerializer(serializers.ModelSerializer):
    """
    Self-registration is for patients only (per the spec: "bemor o'zini
    ro'yxatdan o'tkazadi"). Doctor and admin accounts are provisioned out of
    band (Django admin / the seed_demo_data management command) — opening
    self-registration to those roles would let anyone declare themselves a
    doctor, which is a much bigger permission hole than the assignment is
    asking us to solve.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    # Почта обязательна и уникальна: это единственный контакт пациента и
    # ключ восстановления доступа. Учётки врачей/админов заводятся отдельно
    # (seed / admin) и этим правилом не ограничены.
    email = serializers.EmailField(
        required=True,
        allow_blank=False,
        validators=[UniqueValidator(queryset=User.objects.all(), message="This email is already in use.")],
    )

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(role=User.Role.PATIENT, **validated_data)
        user.set_password(password)
        user.save()
        return user


class AdminUserSerializer(serializers.ModelSerializer):
    """Карточка пользователя для админ-консоли (список и результат правки)."""

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "is_active", "date_joined",
        ]
        read_only_fields = fields


class SelfProfileSerializer(serializers.ModelSerializer):
    """`GET/PATCH /api/auth/me/` — собственные контактные данные.

    Роль, специализация и филиал через этот эндпоинт не меняются: роль
    назначается при создании учётки, а специализацией/филиалом врача по-прежнему
    управляет только администратор (см. AdminDoctorUpdateSerializer). Пароль
    меняется отдельным эндпоинтом `change-password`, не здесь.
    """

    class Meta:
        model = User
        fields = ["id", "username", "email", "first_name", "last_name", "role"]
        read_only_fields = ["id", "username", "role"]

    def validate_email(self, value):
        # Как и при регистрации: email обязателен только у пациента,
        # но если задан — должен быть уникален у любой роли.
        if self.instance.role == User.Role.PATIENT and not value:
            raise serializers.ValidationError("Email is required for patients.")
        if value and User.objects.exclude(pk=self.instance.pk).filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    """`POST /api/auth/change-password/` — смена пароля с подтверждением текущего.

    Отдельно от SelfProfileSerializer намеренно: если бы пароль менялся вместе
    с именем/email в одном PATCH, украденная сессия могла бы сменить пароль
    заодно с безобидной правкой профиля, не зная старого пароля.
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value


class AdminUserUpdateSerializer(serializers.Serializer):
    """Правка любого пользователя из админ-консоли: ФИО, email, активность.

    Роль и пароль этим эндпоинтом не меняются — роль назначается при создании
    учётки, пароль сбрасывается вне API (Django admin) либо меняется самим
    пользователем через change-password.
    """

    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate_email(self, value):
        if self.instance.role == User.Role.PATIENT and not value:
            raise serializers.ValidationError("Email is required for patients.")
        if value and User.objects.exclude(pk=self.instance.pk).filter(email=value).exists():
            raise serializers.ValidationError("This email is already in use.")
        return value

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=list(validated_data))
        return instance

    def to_representation(self, instance):
        return AdminUserSerializer(instance, context=self.context).data


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Adds role/user id to both the JWT payload and the login response body."""

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "role": self.user.role,
        }
        return data
