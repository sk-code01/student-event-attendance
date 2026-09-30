from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from apps.accounts.serializers import PersonBriefSerializer, person_brief
from apps.participation.models import Participation

from .models import ODRequest


class ODRequestSerializer(serializers.ModelSerializer):
    """Read serializer — fully read-only for the same reason as
    AttendanceSerializer: status, reviewer and both review timestamps are
    server-derived and are never accepted as client input."""

    student = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = ODRequest
        fields = [
            'id', 'participation', 'student', 'event', 'reason', 'status',
            'requested_by', 'requested_at', 'reviewed_by', 'reviewed_at', 'rejection_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(PersonBriefSerializer())
    def get_student(self, obj):
        return person_brief(obj.participation.student, include_department=True)

    @extend_schema_field(serializers.DictField())
    def get_event(self, obj):
        event = obj.participation.event
        return {'id': event.id, 'title': event.title, 'event_date': event.event_date, 'venue': event.venue}

    @extend_schema_field(PersonBriefSerializer())
    def get_requested_by(self, obj):
        return person_brief(obj.requested_by)

    @extend_schema_field(PersonBriefSerializer(allow_null=True))
    def get_reviewed_by(self, obj):
        return person_brief(obj.reviewed_by)


class ODRequestCreateSerializer(serializers.Serializer):
    """`participation` plus the justification the Event Coordinator reviews. A participation
    outside the requester's department resolves to 404, never a 400/403 that
    would confirm it exists."""

    participation = serializers.PrimaryKeyRelatedField(queryset=Participation.objects.all())
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)

    def validate_participation(self, participation):
        user = self.context['request'].user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return participation
        if user.department_id is None or participation.event.department_id != user.department_id:
            raise NotFound()
        return participation


class ODRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
