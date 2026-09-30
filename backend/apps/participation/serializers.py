from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.events.models import Event

from .eligibility import get_registration_for_new_participation
from .models import Participation

User = get_user_model()


class _ParticipationStudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class _EventMinimalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ['id', 'title', 'event_date', 'venue', 'status']


class ParticipationSerializer(serializers.ModelSerializer):
    """
    As of Phase 4, capture/evidence detail lives entirely under
    `/api/v1/evidence/` — this serializer only exposes enough to route the
    student there (`evidence_id`) plus a denormalized `evidence_status` for
    list views that would otherwise need an extra round trip per row.
    """

    student = _ParticipationStudentSerializer(read_only=True)
    event = _EventMinimalSerializer(read_only=True)
    evidence_id = serializers.SerializerMethodField()
    evidence_status = serializers.SerializerMethodField()

    class Meta:
        model = Participation
        fields = [
            'id', 'registration', 'student', 'event', 'status',
            'evidence_id', 'evidence_status', 'submitted_at',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_evidence_id(self, obj) -> int | None:
        evidence = getattr(obj, 'evidence', None)
        return evidence.id if evidence else None

    def get_evidence_status(self, obj) -> str | None:
        evidence = getattr(obj, 'evidence', None)
        return evidence.status if evidence else None


class ParticipationOpenSerializer(serializers.Serializer):
    """Opens (or idempotently re-fetches) a Participation for the
    authenticated student. `event` is the only client-supplied field —
    `student`/`registration` are always derived server-side."""

    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())

    def create(self, validated_data):
        user = self.context['request'].user
        event = validated_data['event']
        registration = get_registration_for_new_participation(user, event)

        participation, _created = Participation.objects.get_or_create(registration=registration)
        return participation
