"""Engagement clustering behaviour (§43). Cluster ids are never assumed to
carry meaning; the tests check the centroid-ordered labels."""

from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User

from .helpers import AuthMixin, build_ai_world


class EngagementTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_ai_world()
        self.url = reverse('ai-engagement')

    def _get(self, username):
        self._auth_as(username)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    def test_requires_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_labels_are_ordered_by_engagement_not_cluster_id(self):
        data = self._get('sysadmin')
        self.assertTrue(data['available'])
        self.assertEqual(data['label_order'], ['LOW', 'MODERATE', 'HIGH'])
        scores = [c['engagement_score'] for c in data['centroids']]
        self.assertEqual(scores, sorted(scores))
        self.assertEqual([c['label'] for c in data['centroids']], ['LOW', 'MODERATE', 'HIGH'])

    def test_the_most_active_student_is_high_and_the_cold_one_is_low(self):
        labels = {r['student']: r['label'] for r in self._get('sysadmin')['results']}
        self.assertEqual(labels['studenthigh'], 'HIGH')
        self.assertEqual(labels['studentcold'], 'LOW')
        # Ordering is consistent with the documented formula.
        order = ['LOW', 'MODERATE', 'HIGH']
        self.assertLessEqual(order.index(labels['studentlow']), order.index(labels['studentmid']))
        self.assertLessEqual(order.index(labels['studentmid']), order.index(labels['studenthigh']))

    def test_labels_are_deterministic(self):
        a = {r['student']: r['label'] for r in self._get('sysadmin')['results']}
        b = {r['student']: r['label'] for r in self._get('sysadmin')['results']}
        self.assertEqual(a, b)

    def test_the_engagement_formula_is_documented(self):
        data = self._get('sysadmin')
        self.assertIn('weights', data['engagement_formula'])
        self.assertIn('participations', data['engagement_formula']['weights'])

    def test_student_sees_only_their_own_label(self):
        data = self._get('studenthigh')
        self.assertEqual(data['own']['label'], 'HIGH')
        self.assertIn('Based on your participation history', data['own']['explanation'])
        self.assertIn('not an academic judgment', data['own']['explanation'])
        self.assertEqual(data['results'], [])
        self.assertNotIn('distribution', data)

    def test_event_coordinator_distribution_covers_only_their_department(self):
        data = self._get('hodcs')
        self.assertEqual(data['scoped_students'], 4)  # high, mid, low, cold
        self.assertEqual(sum(data['distribution'].values()), 4)
        students = {r['student'] for r in data['results']}
        self.assertNotIn('studentec', students)

    def test_other_department_event_coordinator_sees_their_own_single_student(self):
        data = self._get('hodec')
        self.assertEqual(data['scoped_students'], 1)
        self.assertEqual({r['student'] for r in data['results']}, {'studentec'})

    def test_faculty_get_distribution_but_no_identities(self):
        data = self._get('facultycs')
        self.assertEqual(sum(data['distribution'].values()), 4)
        self.assertEqual(data['results'], [])

    def test_admin_distribution_is_system_wide(self):
        data = self._get('sysadmin')
        self.assertEqual(data['scoped_students'], 5)
        self.assertEqual(len(data['results']), 5)

    def test_two_students_produce_low_and_high(self):
        User.objects.filter(username__in=['studentmid', 'studentlow', 'studentec']).update(is_active=False)
        data = self._get('sysadmin')
        self.assertEqual(data['k'], 2)
        self.assertEqual(data['label_order'], ['LOW', 'HIGH'])
        labels = {r['student']: r['label'] for r in data['results']}
        self.assertEqual(labels, {'studenthigh': 'HIGH', 'studentcold': 'LOW'})

    def test_one_student_is_insufficient_data(self):
        User.objects.filter(role=User.Role.STUDENT).exclude(username='studenthigh').update(is_active=False)
        data = self._get('sysadmin')
        self.assertFalse(data['available'])
        self.assertEqual(data['reason'], 'INSUFFICIENT_DATA')

    def test_zero_students_is_unavailable(self):
        User.objects.filter(role=User.Role.STUDENT).update(is_active=False)
        data = self._get('sysadmin')
        self.assertFalse(data['available'])

    def test_model_failure_degrades_to_a_controlled_fallback(self):
        with mock.patch('ml.engagement.kmeans.cluster_students', side_effect=RuntimeError('boom')):
            data = self._get('sysadmin')
        self.assertFalse(data['available'])
        self.assertEqual(data['reason'], 'MODEL_ERROR')
        self.assertNotIn('boom', str(data))
