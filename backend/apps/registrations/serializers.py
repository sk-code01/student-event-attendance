from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.events.models import Event
from apps.events.serializers import EventSerializer

from .models import Registration

User = get_user_model()


class _StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email']


class RegistrationSerializer(serializers.ModelSerializer):
    student = _StudentSerializer(read_only=True)
    event = EventSerializer(read_only=True)

    class Meta:
        model = Registration
        fields = ['id', 'student', 'event', 'status', 'registered_at', 'cancelled_at', 'created_at']
        read_only_fields = fields


class RegistrationCreateSerializer(serializers.Serializer):
    """Only the target event is client-supplied — the student is always the
    requesting user, never a client-supplied value (prevents registering on
    someone else's behalf)."""

    event = serializers.PrimaryKeyRelatedField(queryset=Event.objects.all())

    def validate_event(self, event):
        if event.status == Event.Status.DRAFT:
            raise serializers.ValidationError('This event is not open for registration yet.')
        if event.status == Event.Status.CANCELLED:
            raise serializers.ValidationError('This event has been cancelled.')
        if event.status == Event.Status.COMPLETED:
            raise serializers.ValidationError('This event has already concluded.')
        if not event.is_registration_open():
            raise serializers.ValidationError('Registration is not currently open for this event.')
        return event


class _TrackingStudentSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    username = serializers.CharField()
    full_name = serializers.CharField(allow_blank=True)
    university_registration_number = serializers.CharField(allow_null=True)
    department = serializers.CharField(allow_null=True)


class _TrackingEventSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    title = serializers.CharField()
    event_date = serializers.DateField()
    venue = serializers.CharField()
    status = serializers.CharField()


class TrackingRowSerializer(serializers.Serializer):
    """One row of the department-wide tracking view.

    Read-only by construction: every field is derived in
    apps.registrations.tracking from records the caller is already authorized
    to see, and nothing here is ever accepted as input.
    """

    registration_id = serializers.IntegerField()
    student = _TrackingStudentSerializer()
    event = _TrackingEventSerializer()

    registration_status = serializers.CharField()
    registered_at = serializers.DateTimeField()

    participation_id = serializers.IntegerField(allow_null=True)
    participation_status = serializers.CharField(allow_null=True)
    live_capture_status = serializers.CharField()
    live_capture_submitted_at = serializers.DateTimeField(allow_null=True)
    live_capture_location = serializers.CharField(allow_null=True)

    verification_status = serializers.CharField()

    certificate_status = serializers.CharField()
    certificate_attempts_used = serializers.IntegerField()
    certificate_attempts_remaining = serializers.IntegerField()

    attendance_status = serializers.CharField()
    attendance_is_manual = serializers.BooleanField()
    attendance_decided_by = serializers.CharField(allow_null=True)
