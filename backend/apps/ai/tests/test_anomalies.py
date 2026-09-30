"""Anomaly/risk signal behaviour (§42). The output is a signal — the tests
also prove it never changes a record."""

from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import Evidence

from .helpers import AuthMixin, build_ai_world


class AnomalyTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_ai_world()
        self.url = reverse('ai-anomalies')

    def _get(self, username, **params):
        self._auth_as(username)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_requires_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_the_planted_unusual_record_is_ranked_first_with_real_signals(self):
        data = self._get('sysadmin')
        self.assertTrue(data['available'])
        top = data['results'][0]
        self.assertEqual(top['evidence_id'], self.w.ev_unusual.id)
        self.assertIn(top['risk_level'], ('HIGH', 'MEDIUM'))
        signals = ' '.join(top['signals'])
        self.assertIn('5000 m from the venue', signals)
        self.assertIn('resubmitted 1 time', signals)
        self.assertIn('120 minutes after capture', signals)
        self.assertIn('Low GPS accuracy (500 m)', signals)
        self.assertIn('Off-venue warning on 100%', signals)

    def test_normal_records_produce_no_fabricated_signals(self):
        data = self._get('sysadmin')
        normal = [r for r in data['results'] if r['evidence_id'] in self.w.normal_evidence_ids]
        self.assertTrue(normal)
        for row in normal:
            self.assertEqual(row['signals'], [], row)

    def test_the_unusual_record_scores_higher_than_every_normal_one(self):
        data = self._get('sysadmin')
        scores = {r['evidence_id']: r['anomaly_score'] for r in data['results']}
        unusual = scores[self.w.ev_unusual.id]
        for eid in self.w.normal_evidence_ids:
            self.assertGreater(unusual, scores[eid])

    def test_output_is_deterministic(self):
        a = [(r['evidence_id'], r['anomaly_score'], r['risk_level']) for r in self._get('sysadmin')['results']]
        b = [(r['evidence_id'], r['anomaly_score'], r['risk_level']) for r in self._get('sysadmin')['results']]
        self.assertEqual(a, b)

    def test_thresholds_and_feature_definitions_are_documented_in_the_response(self):
        data = self._get('sysadmin')
        self.assertIn('percentile', data['thresholds']['rule'])
        self.assertIn('not a probability', data['score_basis'])
        statuses = {f['temporal_status'] for f in data['feature_definitions']}
        self.assertEqual(statuses, {'PRE-VERIFICATION', 'HISTORICAL'})

    def test_anomaly_features_never_include_the_outcome_of_the_same_record(self):
        names = {f['name'] for f in self._get('sysadmin')['feature_definitions']}
        for forbidden in ('status', 'decision', 'verified', 'rejected'):
            self.assertFalse(any(forbidden in n for n in names), names)

    def test_a_signal_never_changes_the_record(self):
        before = Evidence.objects.get(pk=self.w.ev_unusual.pk).status
        self._get('sysadmin')
        self._get('facultycs')
        after = Evidence.objects.get(pk=self.w.ev_unusual.pk).status
        self.assertEqual(before, after)
        self.assertEqual(after, Evidence.Status.SUBMITTED)  # still awaiting a human

    def test_faculty_see_only_their_department(self):
        ids = {r['evidence_id'] for r in self._get('facultycs')['results']}
        self.assertIn(self.w.ev_unusual.id, ids)
        self.assertNotIn(self.w.ev_ec.id, ids)

    def test_event_coordinator_see_only_their_department(self):
        ids = {r['evidence_id'] for r in self._get('hodec')['results']}
        self.assertEqual(ids, {self.w.ev_ec.id})

    def test_student_sees_only_their_own_evidence(self):
        data = self._get('studentmid')
        students = {r['student'] for r in data['results']}
        self.assertEqual(students, {'studentmid'})
        self.assertIn(self.w.ev_unusual.id, {r['evidence_id'] for r in data['results']})

    def test_single_evidence_filter_outside_scope_is_404(self):
        self._auth_as('hodec')
        self.assertEqual(
            self.client.get(self.url, {'evidence': self.w.ev_unusual.id}).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self._auth_as('studenthigh')
        self.assertEqual(
            self.client.get(self.url, {'evidence': self.w.ev_unusual.id}).status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_single_evidence_filter_inside_scope_returns_only_that_record(self):
        data = self._get('facultycs', evidence=self.w.ev_unusual.id)
        self.assertEqual([r['evidence_id'] for r in data['results']], [self.w.ev_unusual.id])

    def test_non_numeric_evidence_id_is_rejected(self):
        self._auth_as('sysadmin')
        self.assertEqual(self.client.get(self.url, {'evidence': 'x'}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_insufficient_population_is_reported_not_faked(self):
        # Decisions PROTECT their evidence; clear them first so only one
        # evidence record (below MIN_SAMPLES) remains in the population.
        from apps.verification.models import EvidenceVerification
        EvidenceVerification.objects.all().delete()
        Evidence.objects.exclude(pk=self.w.ev_unusual.pk).delete()
        data = self._get('sysadmin')
        self.assertFalse(data['available'])
        self.assertEqual(data['reason'], 'INSUFFICIENT_DATA')

    def test_model_failure_degrades_to_a_controlled_fallback(self):
        with mock.patch('ml.anomaly_detection.isolation_forest.fit_and_score', side_effect=RuntimeError('boom')):
            data = self._get('sysadmin')
        self.assertFalse(data['available'])
        self.assertEqual(data['reason'], 'MODEL_ERROR')
        self.assertNotIn('boom', str(data))
