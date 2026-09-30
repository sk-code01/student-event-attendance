from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.exceptions import NotFound

from apps.accounts.serializers import PersonBriefSerializer, person_brief
from apps.participation.models import Participation
from apps.registrations.models import Registration

from .models import Attendance


class AttendanceSerializer(serializers.ModelSerializer):
    """
    Read serializer. Every field is read-only: status, reviewer and the
    review/request timestamps are server-derived from the authenticated user,
    the endpoint that was called, and the current state — a client can never
    PATCH `status=APPROVED`, name a `reviewed_by`, or backdate `reviewed_at`,
    because none of them is a writable input anywhere in this app.
    """

    student = serializers.SerializerMethodField()
    event = serializers.SerializerMethodField()
    requested_by = serializers.SerializerMethodField()
    reviewed_by = serializers.SerializerMethodField()

    class Meta:
        model = Attendance
        fields = [
            'id', 'participation', 'registration', 'student', 'event', 'status', 'is_manual',
            'requested_by', 'requested_at', 'reviewed_by', 'reviewed_at', 'rejection_reason',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    @extend_schema_field(PersonBriefSerializer())
    def get_student(self, obj):
        student = obj.registration.student if obj.registration_id else obj.participation.student
        return person_brief(student, include_department=True)

    @extend_schema_field(serializers.DictField())
    def get_event(self, obj):
        event = obj.registration.event if obj.registration_id else obj.participation.event
        return {'id': event.id, 'title': event.title, 'event_date': event.event_date, 'venue': event.venue}

    @extend_schema_field(PersonBriefSerializer())
    def get_requested_by(self, obj):
        return person_brief(obj.requested_by)

    @extend_schema_field(PersonBriefSerializer(allow_null=True))
    def get_reviewed_by(self, obj):
        return person_brief(obj.reviewed_by)


class AttendanceMarkSerializer(serializers.Serializer):
    """The Event Coordinator's direct marking input.

    Keyed on the registration rather than the participation, because the whole
    point of this path is the student who never captured and therefore has no
    participation. The department scope is checked here, since there is no
    object to run an object-level permission against at create time.
    """

    registration = serializers.PrimaryKeyRelatedField(queryset=Registration.objects.all())
    status = serializers.ChoiceField(choices=[Attendance.Status.APPROVED, Attendance.Status.REJECTED])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate_registration(self, registration):
        user = self.context['request'].user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return registration
        if user.department_id is None or registration.event.department_id != user.department_id:
            raise serializers.ValidationError('No registration matches this id.')
        return registration

    def validate(self, attrs):
        if attrs['status'] == Attendance.Status.REJECTED and not (attrs.get('reason') or '').strip():
            raise serializers.ValidationError({'reason': 'A reason is required when rejecting attendance.'})
        return attrs


class AttendanceRequestSerializer(serializers.Serializer):
    """`participation` is the only client-supplied field for raising a request.
    A participation the requester cannot see resolves to 404 rather than a
    leaky 400/403 — the same IDOR convention used everywhere in this project —
    which also blocks the "student=A, participation=B-belonging-to-C" spoof
    class outright: there is no separate student field to disagree with the
    participation."""

    participation = serializers.PrimaryKeyRelatedField(queryset=Participation.objects.all())

    def validate_participation(self, participation):
        user = self.context['request'].user
        if user.is_superuser or user.role == user.Role.ADMIN:
            return participation
        if user.department_id is None or participation.event.department_id != user.department_id:
            raise NotFound()
        return participation


class AttendanceRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(allow_blank=False, trim_whitespace=True)
