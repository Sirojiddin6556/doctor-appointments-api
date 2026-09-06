import logging

from rest_framework import filters, generics, mixins, permissions, serializers, status, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer

from apps.common.permissions import IsAdminRole

from .models import User
from .serializers import (
    AdminUserSerializer,
    CustomTokenObtainPairSerializer,
    PatientRegisterSerializer,
)

logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    """Регистрация нового пациента."""

    queryset = User.objects.all()
    serializer_class = PatientRegisterSerializer
    permission_classes = [permissions.AllowAny]

    def perform_create(self, serializer):
        user = serializer.save()
        logger.info("Зарегистрирован новый пациент: %s", user.username)


class CustomTokenObtainPairView(TokenObtainPairView):
    """Выдача JWT-токенов с ограничением частоты запросов."""

    serializer_class = CustomTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny]
    throttle_scope = "login"


class LogoutView(APIView):
    """Выход: переносит переданный refresh-токен в blacklist.

    После этого refresh нельзя использовать для получения нового access —
    сессия действительно завершается, а не только забывается клиентом.
    """

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=inline_serializer(
            "LogoutRequest", {"refresh": serializers.CharField()}
        ),
        responses={205: OpenApiResponse(description="Refresh-токен отозван.")},
    )
    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response(
                {"detail": "Field 'refresh' is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response(
                {"detail": "Token is invalid or already blacklisted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info("Пользователь %s вышел из системы", request.user.username)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class AdminUserViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Список всех пользователей для админ-консоли: ?role=, ?search=."""

    permission_classes = [IsAdminRole]
    serializer_class = AdminUserSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "email", "first_name", "last_name"]

    def get_queryset(self):
        qs = User.objects.order_by("id")
        role = self.request.query_params.get("role")
        if role in User.Role.values:
            qs = qs.filter(role=role)
        return qs
