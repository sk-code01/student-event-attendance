from rest_framework.routers import DefaultRouter

from .views import ActivityViewSet

router = DefaultRouter()
router.register('', ActivityViewSet, basename='activity')

urlpatterns = router.urls
