from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import DoctorViewSet, DoctorWorkingHoursView

router = DefaultRouter()
router.register("", DoctorViewSet, basename="doctor")

# До роутера: иначе шаблон `{pk}` роутера перехватил бы "me" как id врача.
urlpatterns = [
    path("me/working-hours/", DoctorWorkingHoursView.as_view(), name="doctor-working-hours"),
] + router.urls
