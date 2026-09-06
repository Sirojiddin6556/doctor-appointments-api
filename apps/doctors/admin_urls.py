from rest_framework.routers import DefaultRouter

from .admin_views import AdminDoctorViewSet

router = DefaultRouter()
router.register("", AdminDoctorViewSet, basename="admin-doctor")

urlpatterns = router.urls
