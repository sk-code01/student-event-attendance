"""
Analytics endpoints.

Every view follows the same three steps, in this order:

  1. `AnalyticsFilters.from_request` — validate and **scope-check** every
     query parameter. An out-of-scope id is refused here, before any data is
     touched.
  2. `AnalyticsScope` — build role-scoped querysets.
  3. a service function — aggregate.

So scope is applied before aggregation, and a query parameter can only narrow
what the caller is already entitled to.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


from . import services, trends
from .filters import PERIODS, AnalyticsFilters
from .scope import AnalyticsScope
from .serializers import (
    AchievementAnalyticsSerializer,
    ApprovalAnalyticsSerializer,
    DepartmentAnalyticsSerializer,
    EventAnalyticsSerializer,
    OverviewSerializer,
    ParticipationAnalyticsSerializer,
    RegistrationAnalyticsSerializer,
    TrendsSerializer,
    VerificationAnalyticsSerializer,
)

COMMON_PARAMS = [
    OpenApiParameter('date_from', str, description='Inclusive ISO date (YYYY-MM-DD).'),
    OpenApiParameter('date_to', str, description='Inclusive ISO date (YYYY-MM-DD).'),
    OpenApiParameter('event', int, description='Restrict to one event within your scope.'),
    OpenApiParameter('category', str, description='Restrict to one event category (case-insensitive).'),
    OpenApiParameter(
        'department', int,
        description='Admin only may name any department; Event Coordinator/Faculty may name only their own.',
    ),
    OpenApiParameter(
        'student', int,
        description='Staff only, within their own scope. Students always see themselves.',
    ),
]

PERIOD_PARAM = OpenApiParameter(
    'period', str, description=f'Aggregation period: {", ".join(PERIODS)}. Defaults to monthly.',
)


class _AnalyticsView(APIView):
    """Shared plumbing. Subclasses provide `serializer_class` and `compute`."""

    permission_classes = [IsAuthenticated]
    serializer_class = None

    def compute(self, scope, filters):  # pragma: no cover - abstract
        raise NotImplementedError

    def get(self, request):
        filters = AnalyticsFilters.from_request(request)
        scope = AnalyticsScope(user=request.user, filters=filters)
        payload = self.compute(scope, filters)
        return Response(self.serializer_class(payload).data)


@extend_schema(parameters=COMMON_PARAMS, responses=OverviewSerializer, tags=['analytics'])
class OverviewView(_AnalyticsView):
    serializer_class = OverviewSerializer

    def compute(self, scope, filters):
        return services.overview(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=ParticipationAnalyticsSerializer, tags=['analytics'])
class ParticipationView(_AnalyticsView):
    serializer_class = ParticipationAnalyticsSerializer

    def compute(self, scope, filters):
        return services.participation(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=EventAnalyticsSerializer, tags=['analytics'])
class EventsView(_AnalyticsView):
    serializer_class = EventAnalyticsSerializer

    def compute(self, scope, filters):
        return services.events(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=RegistrationAnalyticsSerializer, tags=['analytics'])
class RegistrationsView(_AnalyticsView):
    serializer_class = RegistrationAnalyticsSerializer

    def compute(self, scope, filters):
        return services.registrations(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=ApprovalAnalyticsSerializer, tags=['analytics'])
class AttendanceView(_AnalyticsView):
    serializer_class = ApprovalAnalyticsSerializer

    def compute(self, scope, filters):
        return services.attendance(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=ApprovalAnalyticsSerializer, tags=['analytics'])
class ODView(_AnalyticsView):
    serializer_class = ApprovalAnalyticsSerializer

    def compute(self, scope, filters):
        return services.od(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=AchievementAnalyticsSerializer, tags=['analytics'])
class AchievementsView(_AnalyticsView):
    serializer_class = AchievementAnalyticsSerializer

    def compute(self, scope, filters):
        return services.achievements(scope)


@extend_schema(parameters=COMMON_PARAMS, responses=VerificationAnalyticsSerializer, tags=['analytics'])
class VerificationView(_AnalyticsView):
    serializer_class = VerificationAnalyticsSerializer

    def compute(self, scope, filters):
        return services.verification(scope)


@extend_schema(
    parameters=COMMON_PARAMS + [PERIOD_PARAM], responses=TrendsSerializer, tags=['analytics'],
)
class TrendsView(_AnalyticsView):
    serializer_class = TrendsSerializer

    def compute(self, scope, filters):
        return trends.build_trends(scope, period=filters.period)


@extend_schema(parameters=COMMON_PARAMS, responses=DepartmentAnalyticsSerializer, tags=['analytics'])
class DepartmentsView(_AnalyticsView):
    """Department comparison is restricted to Event Coordinator (own department) and Admin.

    Student and Faculty are refused with 403 rather than handed an empty list,
    because the resource itself is not theirs — the same convention the audit
    trail uses.
    """

    serializer_class = DepartmentAnalyticsSerializer

    def compute(self, scope, filters):
        if not scope.can_see_departments:
            raise PermissionDenied(
                'Department analytics are available to Event Coordinator and Admin accounts only.',
            )
        return services.departments(scope)
