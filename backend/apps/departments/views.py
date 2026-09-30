from rest_framework import viewsets
from rest_framework.permissions import AllowAny

from apps.accounts.permissions import IsAdminRole
from config.pagination import ReferenceDataPagination

from .models import Department
from .serializers import DepartmentSerializer


class DepartmentViewSet(viewsets.ModelViewSet):
    """
    Public read access so the registration form can populate its department
    dropdown without authentication. Write access (create/update/delete) is
    restricted to Admin, since departments are foundational, system-wide
    configuration.
    """

    serializer_class = DepartmentSerializer
    # Reference data feeds dropdowns, not paged tables: the client must be
    # able to ask for all of them in one request (bounded at 200).
    pagination_class = ReferenceDataPagination

    def get_queryset(self):
        queryset = Department.objects.all()
        user = self.request.user
        is_admin = user.is_authenticated and (user.is_superuser or user.role == user.Role.ADMIN)
        if not is_admin:
            queryset = queryset.filter(is_active=True)
        return queryset

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsAdminRole()]
