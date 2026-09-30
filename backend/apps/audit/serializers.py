from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import PersonBriefSerializer, person_brief

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """
    Read-only projection of the existing `AuditLog`. No new audit model was
    introduced in Phase 6 — this simply exposes what Phases 2–5 already write.

    `AuditLog.record()` never stores passwords, JWTs, image bytes or GPS
    values; `description` is a short human sentence written by the service
    layer. So there is nothing to redact here, and nothing is redacted — what
    you see is the whole record.
    """

    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'action', 'description', 'created_at']
        read_only_fields = fields

    @extend_schema_field(PersonBriefSerializer(allow_null=True))
    def get_actor(self, obj):
        # A null actor is a legitimate value meaning "system action".
        return person_brief(obj.actor, include_department=True) if obj.actor_id else None
