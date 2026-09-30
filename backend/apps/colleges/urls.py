from rest_framework.routers import DefaultRouter

from .views import CollegeViewSet

router = DefaultRouter()
router.register('', CollegeViewSet, basename='college')

urlpatterns = router.urls
