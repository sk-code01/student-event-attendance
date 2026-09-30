from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from apps.accounts.serializers import PersonBriefSerializer, person_brief
from apps.participation.models import Participation

from .models import Achievement


class AchievementSerializer(serializers.ModelSerializer):
    """Read serializer. `status`, `created_by`, `reviewed_by` and `reviewed_at`
    are all server-derived and read-only — an achievement can never be created
    or patched straight into APPROVED, and a client can never name its own
    reviewer or review time."""

    student = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()
    is_official = serializers.BooleanField(read_only=True)

    class Meta:
        model = Achievement
        fields = [
            'id', 'participation', 'student', 'event',
            'title', 'description', 'achievement_type', 'achievement_date',
            'status', 'is_official', 'created_by', 'reviewed_by', 'reviewed_at', 'rejection_reason',
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
    def get_created_by(self, obj):
        return person_brief(obj.created_by)

    @extend_schema_field(PersonBriefSerializer(allow_null=True))
    def get_reviewed_by(self, obj):
        return person_brief(obj.reviewed_by)


class AchievementCreateSerializer(serializers.Serializer):
    """The only writable inputs on creation. Note the absence of `student`,
    `event`, `status`, `created_by` and every review field — the student and
    event are derived from `participation` server-side (so the
    "student=A, participation=B" spoof has nothing to target), and the rest
    are decided by the service layer from the authenticated user's role."""

    participation = serializers.PrimaryKeyRelatedField(queryset=Participation.objects.all())
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default='')
    achievement_type = serializers.CharField(max_length=100)
    achievement_date = serializers.DateField()
    submit_for_approval = serializers.BooleanField(
        required=False, default=True,
        help_text=(
            'Faculty only: false keeps the record a DRAFT for further editing instead of '
            'queueing it for Event Coordinator approval. Ignored for Event Coordinator/Admin, '
            'whose records are authoritative on creation.'
        ),
    )

    def validate_participation(self, participation):
        user = self.context['request'].user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return participation
        if user.department_id is None or participation.event.department_id != user.department_id:
            raise NotFound()
        return participation


class AchievementUpdateSerializer(serializers.Serializer):
    """Draft-only editing. `participation` is intentionally not editable — a
    draft cannot be re-pointed at a different student's participation after the
    fact."""

    title = serializers.CharField(max_length=200, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    achievement_type = serializers.CharField(max_length=100, required=False)
    achievement_date = serializers.DateField(required=False)


class AchievementRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
