from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import DashboardSerializer


class DashboardView(APIView):
    """
    `GET /api/v1/dashboard/` — one endpoint, role-aware server-side.

    There is deliberately no `/dashboard/admin/` or `/dashboard/event_coordinator/` variant
    to request: the role is taken from the authenticated user, so there is no
    path for a Student to ask for the Admin payload. Scope is applied while
    building the counts, so unauthorized data is never computed, let alone
    serialized and filtered in Angular.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=DashboardSerializer)
    def get(self, request):
        payload = services.build_dashboard(user=request.user)
        return Response(DashboardSerializer(payload, context={'request': request}).data)
