from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.colleges.models import College
from apps.colleges.serializers import CollegeSerializer

from .models import Event

User = get_user_model()


class _CreatedBySerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username']


class EventSerializer(serializers.ModelSerializer):
    """Read serializer for both list and detail — the field set is small
    enough that a separate lightweight list serializer isn't warranted."""

    conducting_college = CollegeSerializer(read_only=True)
    created_by = _CreatedBySerializer(read_only=True)
    is_registration_open = serializers.SerializerMethodField()
    my_registration_status = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'event_date', 'venue', 'category',
            'venue_latitude', 'venue_longitude',
            'conducting_college', 'created_by', 'status',
            'registration_start_date', 'registration_end_date',
            'is_registration_open', 'my_registration_status',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields

    def get_is_registration_open(self, obj) -> bool:
        return obj.is_registration_open()

    def get_my_registration_status(self, obj) -> str | None:
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated and user.role == user.Role.STUDENT):
            return None
        # The list view prefetches the caller's own registrations onto
        # `my_registrations`; fall back to a query only when it did not.
        prefetched = getattr(obj, 'my_registrations', None)
        if prefetched is not None:
            registration = prefetched[0] if prefetched else None
        else:
            registration = obj.registrations.filter(student=user).first()
        return registration.status if registration else None


class EventWriteSerializer(serializers.ModelSerializer):
    """
    Explicit field whitelist only — `status`, `created_by`, and `department`
    are never accepted from client input (status changes go through the
    dedicated publish/cancel actions; created_by/department are derived
    server-side from the requesting user). This is a deliberate mass-
    assignment guard.
    """

    conducting_college = serializers.PrimaryKeyRelatedField(queryset=College.objects.filter(is_active=True))

    class Meta:
        model = Event
        fields = [
            'id', 'title', 'description', 'event_date', 'venue', 'category',
            'venue_latitude', 'venue_longitude',
            'conducting_college', 'registration_start_date', 'registration_end_date',
        ]
        read_only_fields = ['id']
        extra_kwargs = {
            'venue_latitude': {'required': False},
            'venue_longitude': {'required': False},
        }

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError('Title must be at least 3 characters long.')
        return value

    def validate_venue(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError('Venue must be at least 2 characters long.')
        return value

    def validate_category(self, value):
        value = ' '.join(value.split())
        if len(value) < 2:
            raise serializers.ValidationError('Category must be at least 2 characters long.')
        return value

    def validate(self, attrs):
        # Fall back to the existing instance's values on partial update so a
        # PATCH of just one date field still validates the full date triangle.
        instance = self.instance
        registration_start = attrs.get(
            'registration_start_date', getattr(instance, 'registration_start_date', None),
        )
        registration_end = attrs.get(
            'registration_end_date', getattr(instance, 'registration_end_date', None),
        )
        event_date = attrs.get('event_date', getattr(instance, 'event_date', None))

        if registration_start and registration_end and registration_start > registration_end:
            raise serializers.ValidationError({
                'registration_start_date': 'Registration start date must be on or before the registration end date.',
            })
        if registration_end and event_date and registration_end >= event_date:
            raise serializers.ValidationError({
                'registration_end_date': 'Registration end date must be before the event date.',
            })
        return attrs


class EventStatusActionSerializer(serializers.Serializer):
    """Empty body serializer — publish/cancel actions take no input, just
    used so drf-spectacular documents the action correctly."""
