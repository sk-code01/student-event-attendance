from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .models import Notification
from .serializers import (
    MarkAllReadResponseSerializer,
    NotificationSerializer,
    UnreadCountSerializer,
)


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    A user's own notifications.

    The queryset is filtered to `recipient=request.user` with **no role
    exemption at all** — not even Admin. A notification is a personal message
    with a personal read state, so "system-wide visibility" would mean one
    user marking another's mail as read. Admin gets system-wide oversight
    through the audit endpoints instead, which is the right tool for that job.
    That makes every IDOR case here a plain 404.

    There is no create, update, destroy or partial_update: notifications are
    written only by `apps.notifications.services`, and §42 of the phase spec
    requires history to be preserved, so deletion is not offered.
    """

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Notification.objects.none()
        queryset = Notification.objects.filter(recipient=user)
        unread_only = self.request.query_params.get('unread')
        if unread_only and unread_only.lower() in ('1', 'true', 'yes'):
            queryset = queryset.filter(is_read=False)
        return queryset

    @extend_schema(
        parameters=[OpenApiParameter(
            name='unread', type=bool, required=False,
            description='When true, returns only unread notifications.',
        )],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=None, responses=NotificationSerializer)
    @action(detail=True, methods=['post'])
    def read(self, request, pk=None):
        """Marks one notification read. `get_object()` runs against the
        recipient-filtered queryset, so another user's id is a 404 before any
        write is attempted."""
        notification = self.get_object()
        services.mark_read(notification=notification, user=request.user)
        notification.refresh_from_db()
        return Response(self.get_serializer(notification).data)

    @extend_schema(request=None, responses=MarkAllReadResponseSerializer)
    @action(detail=False, methods=['post'], url_path='read-all')
    def read_all(self, request):
        marked = services.mark_all_read(user=request.user)
        return Response({'marked_read': marked})

    @extend_schema(responses=UnreadCountSerializer)
    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'unread': services.unread_count(user=request.user)})
