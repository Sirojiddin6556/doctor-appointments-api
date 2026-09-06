from rest_framework import generics, permissions
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import User
from .serializers import CustomTokenObtainPairSerializer, PatientRegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — a patient registers themselves."""

    queryset = User.objects.all()
    serializer_class = PatientRegisterSerializer
    permission_classes = [permissions.AllowAny]


class CustomTokenObtainPairView(TokenObtainPairView):
    """POST /api/auth/login/ — JWT access + refresh, rate-limited."""

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"
