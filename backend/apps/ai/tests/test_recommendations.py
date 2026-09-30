"""Recommendation behaviour (§41): content and order, not just HTTP 200."""

from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import AuthMixin, build_ai_world


class RecommendationTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_ai_world()
        self.url = reverse('ai-recommendations')

    def _get(self, username, **params):
        self._auth_as(username)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_requires_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_only_actionable_events_are_recommended(self):
        data = self._get('studenthigh')
        titles = {r['event']['title'] for r in data['results']}
        self.assertNotIn('CS Cancelled', titles)
        self.assertNotIn('CS Closed Window', titles)
        self.assertNotIn('CS Already Registered', titles)
        self.assertNotIn('CS Tech Past', titles)  # registration window closed (ends yesterday)
        self.assertTrue(titles <= {'CS Tech Open', 'CS Cultural Open', 'CS Sports Open', 'EC Open'})

    def test_a_cancelled_registration_can_never_be_recommended_again(self):
        """The unique (student, event) constraint means re-registration is
        impossible, so recommending it would recommend the impossible."""
        from apps.registrations.models import Registration
        reg = Registration.objects.get(student=self.w.student_high, event=self.w.cs_registered_by_high)
        reg.status = Registration.Status.CANCELLED
        reg.save()
        titles = {r['event']['title'] for r in self._get('studenthigh')['results']}
        self.assertNotIn('CS Already Registered', titles)

    def test_knn_ranks_the_categories_the_student_engages_with_first(self):
        """studenthigh's history is 2x Technical + 1x Cultural; Sports is
        entirely new. Technical must outrank Sports."""
        data = self._get('studenthigh')
        self.assertEqual(data['model'], 'knn')
        by_title = {r['event']['title']: r for r in data['results']}
        self.assertGreater(by_title['CS Tech Open']['score'], by_title['CS Sports Open']['score'])
        self.assertEqual(data['results'][0]['event']['title'], 'CS Tech Open')

    def test_knn_reasons_are_backed_by_features(self):
        by_title = {r['event']['title']: r for r in self._get('studenthigh')['results']}
        tech_reasons = ' '.join(by_title['CS Tech Open']['reasons'])
        self.assertIn('Matches a category', tech_reasons)
        self.assertIn('Organised by your department', tech_reasons)
        # Sports is not in the history: no fabricated category match.
        self.assertNotIn('Matches a category', ' '.join(by_title['CS Sports Open']['reasons']))

    def test_knn_is_deterministic(self):
        first = [(r['event_id'], r['score']) for r in self._get('studenthigh')['results']]
        second = [(r['event_id'], r['score']) for r in self._get('studenthigh')['results']]
        self.assertEqual(first, second)

    def test_scores_are_documented_similarities_within_zero_to_one(self):
        data = self._get('studenthigh')
        self.assertIn('Not a probability', data['score_basis'])
        for r in data['results']:
            self.assertGreater(r['score'], 0)
            self.assertLessEqual(r['score'], 1)

    def test_cold_start_is_labelled_honestly_and_prefers_own_department(self):
        data = self._get('studentcold')
        self.assertEqual(data['model'], 'cold_start')
        self.assertEqual(data['history_size'], 0)
        self.assertTrue(data['results'])
        # Every CS event must outrank the EC one for a CS student with no history.
        ranks = {r['event']['title']: i for i, r in enumerate(data['results'])}
        self.assertLess(ranks['CS Tech Open'], ranks['EC Open'])
        self.assertLess(ranks['CS Cultural Open'], ranks['EC Open'])
        self.assertNotIn('Matches a category', ' '.join(
            reason for r in data['results'] for reason in r['reasons']
        ))

    def test_registration_only_history_still_counts_as_engagement_for_knn(self):
        data = self._get('studentlow')
        self.assertEqual(data['model'], 'knn')
        self.assertEqual(data['history_size'], 1)

    def test_no_actionable_events_returns_available_with_a_reason(self):
        from apps.events.models import Event
        Event.objects.filter(status='PUBLISHED').update(status='CANCELLED')
        data = self._get('studenthigh')
        self.assertTrue(data['available'])
        self.assertEqual(data['reason'], 'NO_ACTIONABLE_EVENTS')
        self.assertEqual(data['results'], [])

    def test_limit_is_respected_and_bounded(self):
        self.assertEqual(len(self._get('studenthigh', limit=1)['results']), 1)
        self.assertEqual(self.client.get(self.url, {'limit': 'abc'}).status_code, status.HTTP_400_BAD_REQUEST)

    def test_model_failure_degrades_to_a_controlled_fallback(self):
        with mock.patch('ml.recommendation.knn.score_candidates', side_effect=RuntimeError('boom')):
            data = self._get('studenthigh')
        self.assertFalse(data['available'])
        self.assertEqual(data['reason'], 'MODEL_ERROR')
        self.assertEqual(data['results'], [])
        self.assertNotIn('boom', str(data))  # raw exception text never reaches the client

    def test_staff_cannot_request_recommendations(self):
        for username in ('facultycs', 'hodcs', 'sysadmin'):
            self._auth_as(username)
            self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN, username)

    def test_response_carries_the_disclaimer(self):
        self.assertIn('decision-support', self._get('studenthigh')['disclaimer'])
