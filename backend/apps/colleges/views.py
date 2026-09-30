from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.accounts.permissions import IsAdminRole
from config.pagination import ReferenceDataPagination

from .models import College
from .serializers import CollegeSerializer


class CollegeViewSet(viewsets.ModelViewSet):
    """
    Public read access so event browsing/creation forms can populate a
    college dropdown without authentication. Write access is Admin-only,
    since colleges are foundational, system-wide reference data.
    """

    serializer_class = CollegeSerializer
    # Reference data feeds dropdowns, not paged tables: the client must be
    # able to ask for all of them in one request (bounded at 200).
    pagination_class = ReferenceDataPagination

    def get_queryset(self):
        queryset = College.objects.all()
        user = self.request.user
        is_admin = user.is_authenticated and (user.is_superuser or user.role == user.Role.ADMIN)
        if not is_admin:
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsAdminRole()]
