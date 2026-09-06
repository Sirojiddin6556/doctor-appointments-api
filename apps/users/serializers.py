from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
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

    class Meta:
        model = User
        fields = ["id", "username", "email", "password", "first_name", "last_name"]

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(role=User.Role.PATIENT, **validated_data)
        user.set_password(password)
        user.save()
        return user


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
