from rest_framework.routers import DefaultRouter

from .views import AdminAppointmentViewSet

router = DefaultRouter()
router.register("", AdminAppointmentViewSet, basename="admin-appointment")

urlpatterns = router.urls
