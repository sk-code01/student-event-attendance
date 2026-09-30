from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsStudent
from apps.audit.models import AuditLog
from apps.events.models import Event

from .eligibility import check_participation_eligibility
from .models import Participation
from .permissions import CanAccessParticipation
from .serializers import ParticipationOpenSerializer, ParticipationSerializer


class ParticipationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Deliberately not a full ModelViewSet — a participation is never edited
    or hard-deleted through the API, only opened here and then carried
    through evidence capture/submission under `/api/v1/evidence/` (see
    apps.verification). Capture upload, submission, and image retrieval
    used to live on this viewset in Phase 3; Phase 4 moved all of that onto
    the new Evidence/EvidenceVersion resources so a Participation's capture
    history can be versioned, rather than duplicating that machinery here.
    """

    queryset = Participation.objects.select_related('student', 'event', 'registration', 'evidence')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return ParticipationOpenSerializer
        return ParticipationSerializer

    def get_permissions(self):
        if self.action in ('create', 'eligibility'):
            return [IsAuthenticated(), IsStudent()]
        if self.action == 'retrieve':
            return [IsAuthenticated(), CanAccessParticipation()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if user.is_superuser or user.role == user.Role.ADMIN:
            return queryset
        if user.role == user.Role.EVENT_COORDINATOR:
            return queryset.filter(event__department_id=user.department_id)
        if user.role == user.Role.STUDENT:
            return queryset.filter(student=user)
        return queryset.none()

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            participation = serializer.save()
            AuditLog.record(
                actor=request.user, action='PARTICIPATION_STARTED',
                description=f'Participation #{participation.id} opened for event #{participation.event_id}.',
            )
        return Response(
            ParticipationSerializer(participation, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        parameters=[OpenApiParameter(name='event', type=int, required=True, description='Event id')],
        responses={200: dict},
    )
    @action(detail=False, methods=['get'], url_path='eligibility')
    def eligibility(self, request):
        event_id = request.query_params.get('event')
        if not event_id:
            raise ValidationError({'event': 'This query parameter is required.'})
        try:
            event = Event.objects.get(id=event_id)
        except (Event.DoesNotExist, ValueError):
            raise ValidationError({'event': 'Event not found.'})

        eligible, reason = check_participation_eligibility(request.user, event)
        return Response({
            'eligible': eligible,
            'reason': reason,
            # UX-only: the backend independently re-enforces this on every
            # capture upload regardless of what the client does with it.
            'max_gps_accuracy_meters': settings.MAX_GPS_ACCURACY_METERS,
        })
