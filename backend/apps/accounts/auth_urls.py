"""Mounted at /api/v1/auth/."""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from .views import LogoutView, RegisterView, RegistrationStatusView, RoleAwareTokenObtainPairView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('token/', RoleAwareTokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token-verify'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('registration-status/', RegistrationStatusView.as_view(), name='registration-status'),
]
