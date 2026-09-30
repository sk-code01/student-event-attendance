from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.serializers import PersonBriefSerializer, person_brief

from . import services
from .models import MAX_CERTIFICATE_ATTEMPTS, Certificate, FinalDecision


class CertificateSerializer(serializers.ModelSerializer):
    """Read representation.

    The stored object key and its storage URL are never exposed; the only way
    to read the bytes is the authenticated download endpoint, whose path is
    given here instead.
    """

    student = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()
    final_decided_by = serializers.SerializerMethodField()
    awaits_final_decision = serializers.BooleanField(read_only=True)
    download_url = serializers.SerializerMethodField()
    attempts_used = serializers.SerializerMethodField()
    attempts_remaining = serializers.SerializerMethodField()

    class Meta:
        model = Certificate
        fields = [
            'id', 'participation', 'attempt_number', 'status',
            'original_filename', 'mime_type', 'file_size',
            'student', 'event', 'submitted_at',
            'reviewed_by', 'reviewed_at', 'rejection_reason',
            'final_decision', 'final_decided_by', 'final_decided_at', 'final_rejection_reason',
            'awaits_final_decision',
            'download_url', 'attempts_used', 'attempts_remaining',
        ]
        read_only_fields = fields

    @extend_schema_field(PersonBriefSerializer())
    def get_student(self, obj):
        return person_brief(obj.participation.student, include_department=True)

    @extend_schema_field(serializers.DictField())
    def get_event(self, obj) -> dict:
        event = obj.participation.event
        return {'id': event.id, 'title': event.title, 'event_date': event.event_date}

    @extend_schema_field(PersonBriefSerializer(allow_null=True))
    def get_reviewed_by(self, obj):
        return person_brief(obj.reviewed_by)

    @extend_schema_field(PersonBriefSerializer(allow_null=True))
    def get_final_decided_by(self, obj):
        return person_brief(obj.final_decided_by)

    def get_download_url(self, obj) -> str:
        return f'/api/v1/certificates/{obj.id}/file/'

    def get_attempts_used(self, obj) -> int:
        return services.attempts_used(obj.participation)

    def get_attempts_remaining(self, obj) -> int:
        return services.attempts_remaining(obj.participation)


class CertificateUploadSerializer(serializers.Serializer):
    """Write side of a submission. Only the file is accepted — the attempt
    number, status, hash and owner are all server-derived, so a client cannot
    claim a different attempt or pre-set a decision."""

    participation = serializers.IntegerField()
    file = serializers.FileField()


class CertificateDecisionSerializer(serializers.Serializer):
    """Faculty's verify/reject decision."""

    decision = serializers.ChoiceField(choices=[Certificate.Status.VERIFIED, Certificate.Status.REJECTED])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        if attrs['decision'] == Certificate.Status.REJECTED and not (attrs.get('reason') or '').strip():
            raise serializers.ValidationError({'reason': 'A reason is required when rejecting a certificate.'})
        return attrs


class CertificateEligibilitySerializer(serializers.Serializer):
    """What the student is allowed to do right now, and why not when they
    cannot — the UI needs the reason, not just a disabled button."""

    can_upload = serializers.BooleanField()
    reason = serializers.CharField(allow_null=True)
    window_opens_on = serializers.DateField(allow_null=True)
    attempts_used = serializers.IntegerField()
    attempts_remaining = serializers.IntegerField()
    max_attempts = serializers.IntegerField(default=MAX_CERTIFICATE_ATTEMPTS)


class CertificateFinalDecisionSerializer(serializers.Serializer):
    """The Event Coordinator's final accept/reject on a verified certificate."""

    decision = serializers.ChoiceField(choices=[FinalDecision.ACCEPTED, FinalDecision.REJECTED])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate(self, attrs):
        if attrs['decision'] == FinalDecision.REJECTED and not (attrs.get('reason') or '').strip():
            raise serializers.ValidationError({'reason': 'A reason is required when rejecting a certificate.'})
        return attrs
