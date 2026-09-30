from rest_framework.routers import DefaultRouter

from .views import ODRequestViewSet

router = DefaultRouter()
router.register('', ODRequestViewSet, basename='od-request')

urlpatterns = router.urls
