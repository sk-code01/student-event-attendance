"""
Response schemas for analytics.

These describe aggregate values only. No model instance is ever serialized
here, so there is no path by which a password hash, a JWT, a storage key, an
evidence object reference or unnecessary PII could reach an analytics response
— the underlying services return plain dicts of counts, and the only
identifying values present are ids and display titles/names needed to label a
chart axis.
"""

from rest_framework import serializers


class _Base(serializers.Serializer):
    """Read-only by construction: analytics is a GET-only surface."""

    def create(self, validated_data):  # pragma: no cover - never used
        raise NotImplementedError('Analytics responses are read-only.')

    def update(self, instance, validated_data):  # pragma: no cover - never used
        raise NotImplementedError('Analytics responses are read-only.')


class OverviewSerializer(_Base):
    events = serializers.IntegerField()
    registrations = serializers.IntegerField()
    live_registrations = serializers.IntegerField()
    participations = serializers.IntegerField()
    evidence_submitted = serializers.IntegerField()
    verified_participations = serializers.IntegerField()
    pending_verification = serializers.IntegerField()
    attendance_requests = serializers.IntegerField()
    attendance_approved = serializers.IntegerField()
    od_requests = serializers.IntegerField()
    od_approved = serializers.IntegerField()
    achievements = serializers.IntegerField()
    official_achievements = serializers.IntegerField()
    participation_rate = serializers.FloatField(allow_null=True)
    participation_rate_basis = serializers.CharField()


class EventBreakdownSerializer(_Base):
    event_id = serializers.IntegerField()
    event_title = serializers.CharField()
    participations = serializers.IntegerField(required=False)
    registrations = serializers.IntegerField(required=False)
    requests = serializers.IntegerField(required=False)
    approved = serializers.IntegerField(required=False)
    achievements = serializers.IntegerField(required=False)
    submissions = serializers.IntegerField(required=False)
    verified = serializers.IntegerField(required=False)
    rejected = serializers.IntegerField(required=False)


class CategoryBreakdownSerializer(_Base):
    category = serializers.CharField(allow_blank=True)
    participations = serializers.IntegerField(required=False)
    events = serializers.IntegerField(required=False)


class ParticipationAnalyticsSerializer(_Base):
    total_registrations = serializers.IntegerField()
    live_registrations = serializers.IntegerField()
    total_participations = serializers.IntegerField()
    submitted_participations = serializers.IntegerField()
    draft_participations = serializers.IntegerField()
    verified_participations = serializers.IntegerField()
    pending_verification = serializers.IntegerField()
    rejected_evidence = serializers.IntegerField()
    resubmission_required = serializers.IntegerField()
    participation_rate = serializers.FloatField(allow_null=True)
    participation_rate_basis = serializers.CharField()
    verification_success_rate = serializers.FloatField(allow_null=True)
    verification_success_rate_basis = serializers.CharField()
    by_event = EventBreakdownSerializer(many=True)
    by_category = CategoryBreakdownSerializer(many=True)


class PerEventSerializer(_Base):
    id = serializers.IntegerField()
    title = serializers.CharField()
    event_date = serializers.DateField()
    category = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    registrations = serializers.IntegerField()
    participations = serializers.IntegerField()


class EventAnalyticsSerializer(_Base):
    total_events = serializers.IntegerField()
    draft_events = serializers.IntegerField()
    published_events = serializers.IntegerField()
    cancelled_events = serializers.IntegerField()
    completed_events = serializers.IntegerField()
    by_category = CategoryBreakdownSerializer(many=True)
    per_event = PerEventSerializer(many=True)


class RegistrationAnalyticsSerializer(_Base):
    total_registrations = serializers.IntegerField()
    live_registrations = serializers.IntegerField()
    cancelled_registrations = serializers.IntegerField()
    cancellation_rate = serializers.FloatField(allow_null=True)
    cancellation_rate_basis = serializers.CharField()
    by_event = EventBreakdownSerializer(many=True)


class ApprovalAnalyticsSerializer(_Base):
    """Shared shape for attendance and OD — two independent workflows that
    happen to have the same decision states. They remain separate endpoints and
    separate records; this serializer only avoids duplicating an identical
    schema definition."""

    total_requests = serializers.IntegerField()
    pending = serializers.IntegerField()
    approved = serializers.IntegerField()
    rejected = serializers.IntegerField()
    approval_rate = serializers.FloatField(allow_null=True)
    approval_rate_basis = serializers.CharField()
    by_event = EventBreakdownSerializer(many=True)


class AchievementTypeSerializer(_Base):
    achievement_type = serializers.CharField(allow_blank=True)
    achievements = serializers.IntegerField()
    approved = serializers.IntegerField()


class AchievementAnalyticsSerializer(_Base):
    total_achievements = serializers.IntegerField()
    draft = serializers.IntegerField()
    pending_approval = serializers.IntegerField()
    official_achievements = serializers.IntegerField()
    rejected = serializers.IntegerField()
    approval_rate = serializers.FloatField(allow_null=True)
    approval_rate_basis = serializers.CharField()
    by_type = AchievementTypeSerializer(many=True)
    by_event = EventBreakdownSerializer(many=True)


class VerificationAnalyticsSerializer(_Base):
    total_evidence = serializers.IntegerField()
    pending_review = serializers.IntegerField()
    verified = serializers.IntegerField()
    rejected = serializers.IntegerField()
    resubmission_required = serializers.IntegerField()
    event_coordinator_overrides = serializers.IntegerField()
    verification_rate = serializers.FloatField(allow_null=True)
    verification_rate_basis = serializers.CharField()
    decision_basis = serializers.CharField()
    by_event = EventBreakdownSerializer(many=True)


class DepartmentRowSerializer(_Base):
    department_id = serializers.IntegerField()
    department = serializers.CharField(allow_null=True)
    events = serializers.IntegerField()
    registrations = serializers.IntegerField()
    participations = serializers.IntegerField()
    attendance_approved = serializers.IntegerField()
    od_approved = serializers.IntegerField()
    official_achievements = serializers.IntegerField()


class DepartmentAnalyticsSerializer(_Base):
    departments = DepartmentRowSerializer(many=True)
    department_less_events = serializers.IntegerField()
    department_less_note = serializers.CharField()


class TrendPointSerializer(_Base):
    period = serializers.CharField()
    registrations = serializers.IntegerField()
    participations = serializers.IntegerField()
    verified = serializers.IntegerField()
    attendance_approved = serializers.IntegerField()
    od_approved = serializers.IntegerField()
    achievements = serializers.IntegerField()


class TrendStatisticsSerializer(_Base):
    total = serializers.IntegerField()
    periods = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True)
    latest = serializers.IntegerField(allow_null=True)
    previous = serializers.IntegerField(allow_null=True)
    change = serializers.IntegerField(allow_null=True)
    change_percent = serializers.FloatField(allow_null=True)
    direction = serializers.CharField()
    moving_average_3 = serializers.ListField(child=serializers.FloatField())


class TrendsSerializer(_Base):
    period = serializers.CharField()
    timezone = serializers.CharField()
    series = TrendPointSerializer(many=True)
    statistics = serializers.DictField(child=TrendStatisticsSerializer())
