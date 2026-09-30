from rest_framework import serializers

from apps.audit.serializers import AuditLogSerializer
from apps.notifications.serializers import NotificationSerializer


class DashboardCardSerializer(serializers.Serializer):
    """One operational count.

    `route` is an internal Angular path the card links to — the same
    internal-only rule notifications follow — and never carries a query
    string. Query parameters travel separately in `query` because Angular's
    `routerLink` would encode a "?" into the path rather than parse it.
    """

    key = serializers.CharField(read_only=True)
    label = serializers.CharField(read_only=True)
    value = serializers.IntegerField(read_only=True)
    route = serializers.CharField(read_only=True)
    query = serializers.DictField(child=serializers.CharField(), read_only=True)


class DashboardSerializer(serializers.Serializer):
    """The whole dashboard payload. Entirely read-only and entirely
    server-composed: which cards appear is decided by the role branch in
    apps.dashboard.services, never by client input."""

    role = serializers.CharField(read_only=True)
    cards = DashboardCardSerializer(many=True, read_only=True)
    recent_activity = AuditLogSerializer(many=True, read_only=True)
    recent_notifications = NotificationSerializer(many=True, read_only=True)
    unread_notifications = serializers.IntegerField(read_only=True)
