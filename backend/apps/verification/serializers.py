from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.reverse import reverse

from apps.events.models import Event
from apps.participation.models import Participation

from .models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion

User = get_user_model()


class _EvidenceStudentSerializer(serializers.ModelSerializer):
    department = serializers.CharField(source='department.name', default=None, read_only=True)

    class Meta:
        model = User
        # `full_name` and `university_registration_number` are here because a
        # verifier is matching a person against a register, and a username
        # cannot do that job. `id` remains the technical key.
        fields = [
            'id', 'username', 'full_name', 'university_registration_number',
            'email', 'department',
        ]


class _EvidenceEventSerializer(serializers.ModelSerializer):
    college = serializers.CharField(source='conducting_college.name', default=None, read_only=True)

    class Meta:
        model = Event
        fields = ['id', 'title', 'event_date', 'venue', 'category', 'status', 'college']


class EvidenceCaptureSerializer(serializers.ModelSerializer):
    """Read serializer. `image_url` points at the authenticated download
    endpoint — never the underlying private storage path/URL."""

    image_url = serializers.SerializerMethodField()
    # What a reviewer should read for "where was this taken". The coordinates
    # stay in the payload beside it: requirement 13 asks that the underlying
    # location information is retained for verification, not replaced by a
    # prettier rendering of it.
    location_summary = serializers.CharField(read_only=True)

    class Meta:
        model = EvidenceCapture
        fields = [
            'id', 'capture_role', 'image_url', 'mime_type', 'file_size', 'sha256_hash',
            'device_capture_timestamp', 'server_received_timestamp',
            'latitude', 'longitude', 'gps_accuracy', 'venue_distance', 'location_warning',
            'resolved_address', 'address_precision', 'location_summary',
            'validation_status', 'created_at',
        ]
        read_only_fields = fields

    def get_image_url(self, obj) -> str:
        request = self.context.get('request')
        url = reverse('evidence-capture-image', args=[obj.id])
        return request.build_absolute_uri(url) if request else url


class EvidenceVerificationSerializer(serializers.ModelSerializer):
    reviewer = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceVerification
        fields = ['id', 'reviewer', 'decision', 'reason', 'is_event_coordinator_override', 'created_at']
        read_only_fields = fields

    @extend_schema_field(serializers.DictField())
    def get_reviewer(self, obj):
        return {'id': obj.reviewer_id, 'username': obj.reviewer.username, 'role': obj.reviewer.role}


class EvidenceVersionSerializer(serializers.ModelSerializer):
    captures = EvidenceCaptureSerializer(many=True, read_only=True)
    has_primary_capture = serializers.BooleanField(read_only=True)
    verifications = EvidenceVerificationSerializer(many=True, read_only=True)
    effective_decision = serializers.SerializerMethodField()
    in_progress = serializers.SerializerMethodField()

    class Meta:
        model = EvidenceVersion
        fields = [
            'id', 'version_number', 'submitted_by', 'submission_reason', 'submitted_at', 'created_at',
            'captures', 'has_primary_capture', 'verifications', 'effective_decision', 'in_progress',
        ]
        read_only_fields = fields

    def get_effective_decision(self, obj) -> str | None:
        effective = obj.effective_verification
        return effective.decision if effective else None

    def get_in_progress(self, obj) -> bool:
        return obj.submitted_at is None


class EvidenceSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()
    event = _EvidenceEventSerializer(source='participation.event', read_only=True)
    versions = EvidenceVersionSerializer(many=True, read_only=True)
    current_version_number = serializers.SerializerMethodField()

    class Meta:
        model = Evidence
        fields = [
            'id', 'participation', 'student', 'event', 'status',
            'current_version_number', 'versions', 'created_at', 'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(_EvidenceStudentSerializer())
    def get_student(self, obj):
        return _EvidenceStudentSerializer(obj.participation.student).data

    def get_current_version_number(self, obj) -> int | None:
        return obj.current_version.version_number if obj.current_version else None


class EvidenceOpenSerializer(serializers.Serializer):
    """Opens (or idempotently re-fetches) the current in-progress
    EvidenceVersion for the authenticated student's participation.
    `participation` is the only client-supplied field. A participation id
    that does not belong to the requesting student resolves to 404 (the
    same "outside your visible queryset" convention used everywhere else in
    this project), never a 400/403 that would confirm it exists."""

    participation = serializers.PrimaryKeyRelatedField(queryset=Participation.objects.all())

    def validate_participation(self, participation):
        user = self.context['request'].user
        if participation.student_id != user.id:
            raise NotFound()
        return participation


class EvidenceCaptureCreateSerializer(serializers.Serializer):
    capture_role = serializers.ChoiceField(choices=EvidenceCapture.Role.choices)
    image = serializers.FileField()
    device_capture_timestamp = serializers.DateTimeField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    gps_accuracy = serializers.FloatField()


class DecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default='')


class OverrideSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=EvidenceVerification.Decision.choices)
    reason = serializers.CharField(allow_blank=False)
