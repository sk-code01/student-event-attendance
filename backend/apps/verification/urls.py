from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import (
    EvidenceCaptureImageView,
    EvidenceVersionCaptureUploadView,
    EvidenceVersionSubmitView,
    EvidenceViewSet,
)

router = DefaultRouter()
router.register('', EvidenceViewSet, basename='evidence')

urlpatterns = [
    path('captures/<int:pk>/image/', EvidenceCaptureImageView.as_view(), name='evidence-capture-image'),
    path('versions/<int:version_id>/captures/', EvidenceVersionCaptureUploadView.as_view(),
         name='evidence-version-captures'),
    path('versions/<int:version_id>/submit/', EvidenceVersionSubmitView.as_view(), name='evidence-version-submit'),
    *router.urls,
]
