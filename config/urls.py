"""URL configuration for the clinic appointment API."""

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.users.urls")),
    path("api/doctors/", include("apps.doctors.urls")),
    path("api/slots/", include("apps.slots.urls")),
    path("api/appointments/", include("apps.appointments.urls")),
    path("api/admin/appointments/", include("apps.appointments.admin_urls")),
    # Bonus: OpenAPI schema + Swagger UI at /api/docs/
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
