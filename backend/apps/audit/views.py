"""
Read-only presentation of the existing AuditLog.

Three distinct scopes, deliberately on two endpoints rather than one
role-switching one, because "my own activity" and "the system audit trail" are
different products with different audiences:

  * `GET /api/v1/activity/`  — every authenticated user's *own* recent actions,
    a human-readable feed. Never another user's.
  * `GET /api/v1/audit/`     — the administrative trail. Admin sees everything;
    an Event Coordinator sees only actions performed by members of their own department;
    Student and Faculty are refused outright.

No Activity table was created. The phase spec asks for one only if there is a
real architectural reason, and there is not: AuditLog already records every
business action with an actor and a timestamp, so activity is a filtered read
of it. Duplicating every audit row into a second table would double the write
cost and create two sources of truth that can disagree. If this read ever
becomes a performance problem, a denormalised feed table is the documented
future optimisation — not a Phase 6 requirement.
"""

from datetime import datetime

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated

from apps.accounts.models import User

from .models import AuditLog
from .serializers import AuditLogSerializer

_FILTER_PARAMS = [
    OpenApiParameter(name='action', type=str, required=False,
                     description='Exact audit action code, e.g. ATTENDANCE_APPROVED.'),
    OpenApiParameter(name='actor', type=int, required=False, description='Filter by actor user id.'),
    OpenApiParameter(name='date_from', type=str, required=False, description='ISO date, inclusive.'),
    OpenApiParameter(name='date_to', type=str, required=False, description='ISO date, inclusive.'),
    OpenApiParameter(name='search', type=str, required=False, description='Substring match on description.'),
]


def _parse_date(raw, field):
    """A malformed date is a 400. Passing the raw string into a `__date`
    lookup would make Django raise ValidationError inside the ORM, which DRF
    does not translate - the request would 500."""
    try:
        return datetime.strptime(raw.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        raise ValidationError({field: 'Expected an ISO date in YYYY-MM-DD format.'})


def _apply_filters(queryset, params):
    action = params.get('action')
    if action:
        queryset = queryset.filter(action=action.upper())
    actor = params.get('actor')
    if actor:
        if not actor.isdigit():
            raise ValidationError({'actor': 'Expected a numeric user id.'})
        queryset = queryset.filter(actor_id=int(actor))
    date_from = params.get('date_from')
    if date_from:
        queryset = queryset.filter(created_at__date__gte=_parse_date(date_from, 'date_from'))
    date_to = params.get('date_to')
    if date_to:
        queryset = queryset.filter(created_at__date__lte=_parse_date(date_to, 'date_to'))
    search = params.get('search')
    if search:
        queryset = queryset.filter(description__icontains=search)
    return queryset


class ActivityViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The caller's own recent actions. Scope is `actor=request.user` with no
    role exemption, so this endpoint can never leak another user's history —
    not even to Admin, who has `/audit/` for that."""

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return AuditLog.objects.none()
        return _apply_filters(
            AuditLog.objects.select_related('actor__department').filter(actor=user),
            self.request.query_params,
        )

    @extend_schema(parameters=_FILTER_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)


class AuditLogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    The administrative audit trail.

    Admin/superuser: system-wide. Event Coordinator: restricted to actions performed by
    users in their own department (plus their own), which is the closest
    honest department scope available — `AuditLog` records an actor but not a
    target entity, so scoping is by who acted. Student and Faculty are refused
    with 403 rather than being given an empty list, because the resource
    itself is not theirs to query.
    """

    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return AuditLog.objects.none()

        queryset = AuditLog.objects.select_related('actor__department')
        if user.is_superuser or user.role == User.Role.ADMIN:
            pass
        elif user.role == User.Role.EVENT_COORDINATOR:
            if user.department_id is None:
                queryset = queryset.filter(actor=user)
            else:
                queryset = queryset.filter(
                    Q(actor__department_id=user.department_id) | Q(actor=user),
                )
        else:
            raise PermissionDenied('The audit trail is available to Event Coordinator and Admin accounts only.')
        return _apply_filters(queryset, self.request.query_params)

    @extend_schema(parameters=_FILTER_PARAMS)
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
