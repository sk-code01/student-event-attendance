"""
AI endpoints. Three, each GET-only, each authenticated, each scoped by the
same `AnalyticsScope` boundary analytics and reports use.

  GET /api/v1/recommendations/   Student only — their own, no student parameter
  GET /api/v1/anomalies/         evidence risk signals within the caller's scope
  GET /api/v1/engagement/        own label (Student) / scoped distribution (staff)

There is deliberately no `?student=` on recommendations or engagement: the
subject is always `request.user`, so there is no id to tamper with. Anomalies
accept `?evidence=<id>`, resolved against the scoped queryset first — an id
outside it is a 404 before any model runs.
"""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.analytics.scope import AnalyticsScope

from . import services
from .serializers import (
    AnomaliesResponseSerializer,
    EngagementResponseSerializer,
    RecommendationsResponseSerializer,
)


@extend_schema(
    parameters=[OpenApiParameter('limit', int, description='Maximum recommendations (1-50, default 10).')],
    responses=RecommendationsResponseSerializer, tags=['ai'],
)
class RecommendationsView(APIView):
    """Personalised, actionable event recommendations for the requesting
    student. Staff accounts are refused: a recommendation is personal to one
    student's history, and no administrative workflow in this system needs to
    view another person's."""

    permission_classes = [IsAuthenticated]
    throttle_scope = 'ai'

    def get(self, request):
        user = request.user
        if user.role != User.Role.STUDENT and not user.is_superuser:
            raise PermissionDenied('Event recommendations are personal to student accounts.')
        limit = _limit(request.query_params.get('limit'))
        payload = services.recommend_events(user, limit=limit)
        return Response(RecommendationsResponseSerializer(payload).data)


@extend_schema(
    parameters=[
        OpenApiParameter('evidence', int, description='Restrict to one evidence record within your scope.'),
        OpenApiParameter('limit', int, description='Maximum rows (1-500, default 100).'),
    ],
    responses=AnomaliesResponseSerializer, tags=['ai'],
)
class AnomaliesView(APIView):
    """Isolation Forest risk signals for evidence the caller may already
    review. A signal is a prompt for human attention; it never changes a
    record."""

    permission_classes = [IsAuthenticated]
    throttle_scope = 'ai'

    def get(self, request):
        scope = AnalyticsScope(user=request.user)
        evidence_id = None
        raw = request.query_params.get('evidence')
        if raw:
            if not str(raw).isdigit():
                raise ValidationError({'evidence': 'Expected a numeric evidence id.'})
            evidence_id = int(raw)
            # Scoped queryset first: an id the caller cannot see is a plain 404,
            # never a hint that it exists.
            if not scope.evidence().filter(id=evidence_id).exists():
                raise NotFound('Evidence not found.')
        limit = _limit(request.query_params.get('limit'), default=100, maximum=500)
        payload = services.evidence_risk_signals(scope=scope, evidence_id=evidence_id, limit=limit)
        return Response(AnomaliesResponseSerializer(payload).data)


@extend_schema(responses=EngagementResponseSerializer, tags=['ai'])
class EngagementView(APIView):
    """K-Means engagement clusters. Students see their own label only; Faculty
    see their department's distribution; Event Coordinator and Admin also see per-student
    labels inside their scope."""

    permission_classes = [IsAuthenticated]
    throttle_scope = 'ai'

    def get(self, request):
        scope = AnalyticsScope(user=request.user)
        payload = services.engagement(scope=scope, user=request.user)
        return Response(EngagementResponseSerializer(payload).data)


def _limit(raw, *, default=10, maximum=50):
    if raw is None or raw == '':
        return default
    if not str(raw).isdigit():
        raise ValidationError({'limit': 'Expected a positive integer.'})
    return max(1, min(int(raw), maximum))
