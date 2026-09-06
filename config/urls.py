"""Маршруты API записи пациентов в клинику."""

from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def frontend(request):
    return render(request, "frontend/index.html")


def healthz(request):
    """Liveness/readiness: процесс жив и база отвечает."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:  # noqa: BLE001 — любой сбой БД = сервис не готов
        return JsonResponse({"status": "db-unavailable"}, status=503)


urlpatterns = [
    path("", frontend, name="frontend"),
    path("healthz/", healthz, name="healthz"),
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/doctors/", include("apps.doctors.urls")),
    path("api/slots/", include("apps.slots.urls")),
    path("api/appointments/", include("apps.appointments.urls")),
    path("api/admin/appointments/", include("apps.appointments.admin_urls")),
    path("api/admin/doctors/", include("apps.doctors.admin_urls")),
    path("api/admin/users/", include("apps.users.admin_urls")),
    # OpenAPI-схема и Swagger UI доступны по адресу /api/docs/.
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]

urlpatterns += staticfiles_urlpatterns()
