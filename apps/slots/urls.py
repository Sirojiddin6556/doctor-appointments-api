from rest_framework.routers import DefaultRouter

from .views import SlotViewSet

router = DefaultRouter()
router.register("", SlotViewSet, basename="slot")

urlpatterns = router.urls
