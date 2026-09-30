"""
Response schemas for the AI endpoints. All read-only; nothing here accepts
input. `available` is always present so a client can branch on it before
reading any model-specific field.
"""

from rest_framework import serializers


class _ReadOnly(serializers.Serializer):
    def create(self, validated_data):  # pragma: no cover
        raise NotImplementedError

    def update(self, instance, validated_data):  # pragma: no cover
        raise NotImplementedError


class _AIBase(_ReadOnly):
    available = serializers.BooleanField()
    model = serializers.CharField(help_text='knn | cold_start | isolation_forest | kmeans')
    model_version = serializers.CharField(required=False)
    feature_version = serializers.CharField(required=False)
    reason = serializers.CharField(required=False, help_text='Set when available is false or results are empty.')
    detail = serializers.CharField(required=False, allow_blank=True)
    generated_at = serializers.DateTimeField()
    disclaimer = serializers.CharField()
    inference_ms = serializers.FloatField()


class RecommendedEventSerializer(_ReadOnly):
    id = serializers.IntegerField()
    title = serializers.CharField()
    category = serializers.CharField(allow_blank=True)
    event_date = serializers.DateField()
    venue = serializers.CharField()
    registration_end_date = serializers.DateField()
    department = serializers.CharField(allow_null=True)


class RecommendationSerializer(_ReadOnly):
    event_id = serializers.IntegerField()
    score = serializers.FloatField(help_text='Similarity or cold-start ranking score in (0, 1]. Not a probability.')
    reasons = serializers.ListField(child=serializers.CharField())
    event = RecommendedEventSerializer()


class RecommendationsResponseSerializer(_AIBase):
    score_basis = serializers.CharField(required=False)
    history_size = serializers.IntegerField(required=False)
    candidate_count = serializers.IntegerField(required=False)
    results = RecommendationSerializer(many=True)


class AnomalyThresholdsSerializer(_ReadOnly):
    high = serializers.FloatField()
    medium = serializers.FloatField()
    rule = serializers.CharField()


class FeatureDefinitionSerializer(_ReadOnly):
    name = serializers.CharField()
    temporal_status = serializers.CharField()


class PopulationSerializer(_ReadOnly):
    n_samples = serializers.IntegerField()
    n_features = serializers.IntegerField()


class RiskSignalSerializer(_ReadOnly):
    evidence_id = serializers.IntegerField()
    participation_id = serializers.IntegerField(allow_null=True)
    student = serializers.CharField(allow_null=True)
    event_id = serializers.IntegerField(allow_null=True)
    event_title = serializers.CharField(allow_null=True)
    effective_decision = serializers.CharField(allow_null=True)
    risk_level = serializers.ChoiceField(choices=['LOW', 'MEDIUM', 'HIGH'])
    anomaly_score = serializers.FloatField(help_text='Higher = more isolated. Not a probability.')
    signals = serializers.ListField(child=serializers.CharField())
    features = serializers.DictField(child=serializers.FloatField(allow_null=True))


class AnomaliesResponseSerializer(_AIBase):
    score_basis = serializers.CharField(required=False)
    thresholds = AnomalyThresholdsSerializer(required=False)
    population = PopulationSerializer(required=False)
    feature_definitions = FeatureDefinitionSerializer(many=True, required=False)
    summary = serializers.DictField(child=serializers.IntegerField(), required=False)
    results = RiskSignalSerializer(many=True)


class CentroidSerializer(_ReadOnly):
    label = serializers.CharField()
    engagement_score = serializers.FloatField()
    features = serializers.DictField(child=serializers.FloatField())


class EngagementFormulaSerializer(_ReadOnly):
    description = serializers.CharField()
    weights = serializers.DictField(child=serializers.FloatField())


class OwnEngagementSerializer(_ReadOnly):
    label = serializers.ChoiceField(choices=['LOW', 'MODERATE', 'HIGH'])
    features = serializers.DictField(child=serializers.FloatField())
    explanation = serializers.CharField()


class StudentEngagementSerializer(_ReadOnly):
    student_id = serializers.IntegerField()
    student = serializers.CharField(allow_null=True)
    label = serializers.ChoiceField(choices=['LOW', 'MODERATE', 'HIGH'])
    features = serializers.DictField(child=serializers.FloatField())


class EngagementResponseSerializer(_AIBase):
    k = serializers.IntegerField(required=False)
    label_order = serializers.ListField(child=serializers.CharField(), required=False)
    population = PopulationSerializer(required=False)
    centroids = CentroidSerializer(many=True, required=False)
    engagement_formula = EngagementFormulaSerializer(required=False)
    note = serializers.CharField(required=False, allow_blank=True)
    own = OwnEngagementSerializer(required=False, allow_null=True)
    distribution = serializers.DictField(child=serializers.IntegerField(), required=False)
    scoped_students = serializers.IntegerField(required=False)
    results = StudentEngagementSerializer(many=True)
