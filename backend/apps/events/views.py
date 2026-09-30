from django.db import models as django_models, transaction
from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from apps.audit.models import AuditLog
from apps.notifications import services as notifications

from .models import Event
from .permissions import IsEventManager
from .serializers import EventSerializer, EventStatusActionSerializer, EventWriteSerializer


class EventViewSet(viewsets.ModelViewSet):
    permission_classes = [IsEventManager]

    def get_serializer_class(self):
        if self.action in ('create', 'update', 'partial_update'):
            return EventWriteSerializer
        return EventSerializer

    def get_queryset(self):
        Event.objects.mark_past_events_completed()

        queryset = Event.objects.select_related('conducting_college', 'created_by', 'department')
        user = self.request.user
        if not user.is_authenticated:
            return queryset.none()
        if user.role == user.Role.STUDENT:
            # `my_registration_status` is per-event; without this prefetch the
            # serializer issues one registration query per event in the list.
            from apps.registrations.models import Registration
            queryset = queryset.prefetch_related(Prefetch(
                'registrations', queryset=Registration.objects.filter(student=user), to_attr='my_registrations',
            ))

        if user.is_superuser or user.role == user.Role.ADMIN:
            return queryset
        if user.role == user.Role.EVENT_COORDINATOR:
            return queryset.filter(
                django_models.Q(department_id=user.department_id)
                | ~django_models.Q(status=Event.Status.DRAFT),
            )
        # Faculty and Student: draft events are an authoring/preparation
        # state and are never visible outside the managing department.
        return queryset.exclude(status=Event.Status.DRAFT)

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        department = user.department if user.role == user.Role.EVENT_COORDINATOR else None
        event = serializer.save(created_by=user, department=department)
        AuditLog.record(
            actor=user, action='EVENT_CREATED',
            description=f'Event #{event.id} "{event.title}" created (status={event.status}).',
        )

    @transaction.atomic
    def perform_update(self, serializer):
        instance = serializer.instance
        if instance.status in (Event.Status.CANCELLED, Event.Status.COMPLETED):
            raise ValidationError(f'Cannot edit an event that is {instance.status.lower()}.')
        event = serializer.save()
        AuditLog.record(
            actor=self.request.user, action='EVENT_UPDATED',
            description=f'Event #{event.id} "{event.title}" updated.',
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if not (request.user.is_superuser or request.user.role == request.user.Role.ADMIN):
            raise PermissionDenied('Only Admin can delete events.')
        if instance.registrations.exists():
            raise ValidationError('Cannot delete an event that has registrations. Cancel it instead.')
        return super().destroy(request, *args, **kwargs)

    @extend_schema(request=EventStatusActionSerializer, responses=EventSerializer)
    @action(detail=True, methods=['post'])
    def publish(self, request, pk=None):
        event = self.get_object()
        if event.status != Event.Status.DRAFT:
            return Response(
                {'detail': f'Cannot publish an event that is {event.status.lower()}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            event.status = Event.Status.PUBLISHED
            event.save(update_fields=['status', 'updated_at'])
            AuditLog.record(
                actor=request.user, action='EVENT_PUBLISHED',
                description=f'Event #{event.id} "{event.title}" published.',
            )
            notifications.schedule(notifications.notify_event_published, event=event)
        return Response(EventSerializer(event, context={'request': request}).data)

    @extend_schema(request=EventStatusActionSerializer, responses=EventSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        event = self.get_object()
        if event.status not in (Event.Status.DRAFT, Event.Status.PUBLISHED):
            return Response(
                {'detail': f'Cannot cancel an event that is {event.status.lower()}.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            event.status = Event.Status.CANCELLED
            event.save(update_fields=['status', 'updated_at'])
            # Existing registrations are intentionally left as-is (see
            # Registration model docs) — the event's own status is the source of
            # truth for "this registration's event was cancelled".
            AuditLog.record(
                actor=request.user, action='EVENT_CANCELLED',
                description=f'Event #{event.id} "{event.title}" cancelled.',
            )
            notifications.schedule(notifications.notify_event_cancelled, event=event)
        return Response(EventSerializer(event, context={'request': request}).data)
