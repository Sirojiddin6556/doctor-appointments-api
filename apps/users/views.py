import logging

from django.db.models import ProtectedError
from rest_framework import filters, generics, mixins, permissions, serializers, status, viewsets
from rest_framework.exceptions import ValidationError
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
    AdminUserUpdateSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
    PatientRegisterSerializer,
    SelfProfileSerializer,
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


class MeView(generics.RetrieveUpdateAPIView):
    """`GET/PATCH /api/auth/me/` — собственные ФИО и email для любой роли."""

    serializer_class = SelfProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = serializer.save()
        logger.info("Пользователь %s обновил собственный профиль", user.username)


class ChangePasswordView(APIView):
    """`POST /api/auth/change-password/` — смена пароля с проверкой текущего."""

    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=ChangePasswordSerializer,
        responses={204: OpenApiResponse(description="Пароль изменён.")},
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        logger.info("Пользователь %s сменил пароль", request.user.username)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminUserViewSet(
    mixins.ListModelMixin, mixins.UpdateModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """Управление пользователями из админ-консоли: список, правка, удаление.

    Роль и пароль этим эндпоинтом не меняются (см. AdminUserUpdateSerializer).
    Создание новой учётки — через регистрацию (пациент) или
    POST /api/admin/doctors/ (врач); учётку админа заводит seed / Django admin.
    """

    permission_classes = [IsAdminRole]
    filter_backends = [filters.SearchFilter]
    search_fields = ["username", "email", "first_name", "last_name"]

    def get_serializer_class(self):
        if self.action in ("update", "partial_update"):
            return AdminUserUpdateSerializer
        return AdminUserSerializer

    def get_queryset(self):
        qs = User.objects.order_by("id")
        role = self.request.query_params.get("role")
        if role in User.Role.values:
            qs = qs.filter(role=role)
        return qs

    def perform_update(self, serializer):
        user = serializer.save()
        logger.info("Админ %s изменил пользователя %s", self.request.user.username, user.username)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise ValidationError({"detail": "You cannot delete your own account."})
        username = user.username
        try:
            # Doctor каскадирует с User; Appointment.patient/slot стоят на
            # PROTECT, поэтому у пользователя с историей записей удаление
            # отклоняется — та же схема, что и у AdminDoctorViewSet.destroy.
            user.delete()
        except ProtectedError:
            return Response(
                {
                    "detail": "Нельзя удалить пользователя: есть защищённые связанные записи "
                    "(например, appointments). Отключите учётную запись (is_active=false)."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        logger.info("Админ %s удалил пользователя %s", request.user.username, username)
        return Response(status=status.HTTP_204_NO_CONTENT)
