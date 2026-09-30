from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Fully read-only. There is no writable field anywhere in this app:
    `recipient` is chosen by the notification service from the business
    object, and `is_read`/`read_at` change only through the dedicated
    read/read-all actions, which stamp the server clock. A client therefore
    cannot address a notification at someone else, forge a read time, or
    backdate `created_at`."""

    class Meta:
        model = Notification
        fields = [
            'id', 'notification_type', 'title', 'message',
            'related_entity_type', 'related_entity_id', 'action_route',
            'priority', 'is_read', 'read_at', 'created_at',
        ]
        read_only_fields = fields


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField(read_only=True)


class MarkAllReadResponseSerializer(serializers.Serializer):
    marked_read = serializers.IntegerField(read_only=True)
