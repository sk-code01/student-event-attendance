from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CertificateFileView, CertificateViewSet

router = DefaultRouter()
router.register('', CertificateViewSet, basename='certificate')

urlpatterns = [
    # Declared before the router so the router's detail route does not swallow
    # `<pk>/file/` as a lookup value.
    path('<int:pk>/file/', CertificateFileView.as_view(), name='certificate-file'),
    path('', include(router.urls)),
]
