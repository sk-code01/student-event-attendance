"""
Data-leakage matrix (§44), business-workflow safety (§45) and performance
(§46).

The leakage tests attempt what an attacker would: naming someone else. The
safety tests prove the structural guarantee — no business service imports the
AI layer — and then demonstrate it by breaking the models while running every
core workflow.
"""

import pathlib
import time
from unittest import mock

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.od.models import ODRequest
from apps.verification.models import Evidence

from .helpers import AuthMixin, build_ai_world, evidence_with_capture, make_participation, make_student


class LeakageTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_ai_world()

    def test_student_cannot_name_another_student_on_any_ai_endpoint(self):
        """There is no student parameter at all; passing one must be ignored,
        never honoured."""
        self._auth_as('studentcold')
        for name in ('ai-recommendations', 'ai-engagement', 'ai-anomalies'):
            response = self.client.get(reverse(name), {'student': self.w.student_high.id,
                                                       'student_id': self.w.student_high.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, name)
            body = str(response.data)
            self.assertNotIn('studenthigh', body, name)

    def test_student_engagement_never_includes_other_students(self):
        self._auth_as('studentcold')
        data = self.client.get(reverse('ai-engagement')).data
        self.assertEqual(data['results'], [])
        self.assertNotIn('distribution', data)

    def test_student_anomalies_never_include_other_students(self):
        self._auth_as('studenthigh')
        data = self.client.get(reverse('ai-anomalies')).data
        self.assertEqual({r['student'] for r in data['results']}, {'studenthigh'})

    def test_faculty_cannot_reach_another_department(self):
        self._auth_as('facultycs')
        anomalies = self.client.get(reverse('ai-anomalies'), {'department': self.w.ec.id}).data
        self.assertNotIn('studentec', str(anomalies['results']))
        engagement = self.client.get(reverse('ai-engagement'), {'department': self.w.ec.id}).data
        self.assertEqual(engagement['scoped_students'], 4)

    def test_event_coordinator_cannot_reach_another_department(self):
        self._auth_as('hodcs')
        for name in ('ai-anomalies', 'ai-engagement'):
            body = str(self.client.get(reverse(name), {'department': self.w.ec.id}).data)
            self.assertNotIn('studentec', body, name)

    def test_event_coordinator_and_faculty_are_not_system_wide(self):
        self._auth_as('hodcs')
        self.assertEqual(self.client.get(reverse('ai-engagement')).data['scoped_students'], 4)
        self._auth_as('facultycs')
        self.assertEqual(self.client.get(reverse('ai-engagement')).data['scoped_students'], 4)
        self._auth_as('sysadmin')
        self.assertEqual(self.client.get(reverse('ai-engagement')).data['scoped_students'], 5)

    def test_no_ai_response_carries_credentials_or_private_references(self):
        self._auth_as('sysadmin')
        for name in ('ai-anomalies', 'ai-engagement'):
            body = str(self.client.get(reverse(name)).data).lower()
            for needle in ('password', 'pbkdf2', 'bearer', 'refresh', 'sha256', 'object_reference',
                           'participation_captures', 'latitude', 'longitude'):
                self.assertNotIn(needle, body, f'{name} leaked {needle!r}')


class WorkflowSafetyTests(AuthMixin, APITestCase):
    """AI failure must never touch a core workflow."""

    BUSINESS_MODULES = [
        'apps/registrations/views.py', 'apps/registrations/serializers.py',
        'apps/participation/views.py', 'apps/participation/eligibility.py',
        'apps/verification/services.py', 'apps/verification/views.py',
        'apps/attendance/services.py', 'apps/od/services.py', 'apps/achievements/services.py',
        'apps/notifications/services.py', 'apps/events/views.py',
    ]

    def setUp(self):
        self.w = build_ai_world()

    def test_no_business_module_imports_the_ai_layer(self):
        """The structural guarantee: with no import there is no call, and with
        no call there is no transaction for an AI failure to roll back."""
        root = pathlib.Path(__file__).resolve().parents[3]  # tests/ -> ai/ -> apps/ -> backend/
        for relative in self.BUSINESS_MODULES:
            source = (root / relative).read_text(encoding='utf-8')
            self.assertNotIn('apps.ai', source, relative)
            self.assertNotIn('from ml', source, relative)
            self.assertNotIn('import ml', source, relative)

    def test_every_core_workflow_succeeds_while_every_model_is_broken(self):
        broken = RuntimeError('every model is down')
        with mock.patch('ml.recommendation.knn.score_candidates', side_effect=broken), \
             mock.patch('ml.anomaly_detection.isolation_forest.fit_and_score', side_effect=broken), \
             mock.patch('ml.engagement.kmeans.cluster_students', side_effect=broken):

            # Registration
            self._auth_as('studentcold')
            r = self.client.post(reverse('registration-list'), {'event': self.w.cs_tech_open.id})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

            # Evidence verification (Faculty)
            self._auth_as('facultycs')
            r = self.client.post(reverse('evidence-verify', args=[self.w.ev_unusual.id]), {'reason': 'ok'})
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
            self.assertEqual(Evidence.objects.get(pk=self.w.ev_unusual.pk).status, Evidence.Status.VERIFIED)

            # Attendance and OD requests
            r = self.client.post(reverse('attendance-list'), {'participation': self.w.p_unusual.id})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)
            r = self.client.post(reverse('od-request-list'),
                                 {'participation': self.w.p_unusual.id, 'reason': 'fest'})
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

            # Achievement
            r = self.client.post(reverse('achievement-list'), {
                'participation': self.w.p_unusual.id, 'title': 'Prize', 'achievement_type': 'Competition',
                'achievement_date': str(self.w.cs_cultural_past.event_date),
            })
            self.assertEqual(r.status_code, status.HTTP_201_CREATED, r.data)

            # Event Coordinator decisions
            self._auth_as('hodcs')
            attendance = Attendance.objects.get(participation=self.w.p_unusual)
            r = self.client.post(reverse('attendance-approve', args=[attendance.id]))
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)
            od = ODRequest.objects.get(participation=self.w.p_unusual)
            r = self.client.post(reverse('od-request-approve', args=[od.id]))
            self.assertEqual(r.status_code, status.HTTP_200_OK, r.data)

            # And the AI endpoints themselves degrade rather than 500.
            for name in ('ai-anomalies', 'ai-engagement'):
                r = self.client.get(reverse(name))
                self.assertEqual(r.status_code, status.HTTP_200_OK, name)
                self.assertFalse(r.data['available'])
                self.assertEqual(r.data['reason'], 'MODEL_ERROR')

    def test_a_high_risk_signal_does_not_reject_or_alter_evidence(self):
        self._auth_as('facultycs')
        data = self.client.get(reverse('ai-anomalies'), {'evidence': self.w.ev_unusual.id}).data
        self.assertIn(data['results'][0]['risk_level'], ('HIGH', 'MEDIUM'))
        refreshed = Evidence.objects.get(pk=self.w.ev_unusual.pk)
        self.assertEqual(refreshed.status, Evidence.Status.SUBMITTED)
        self.assertFalse(refreshed.current_version.verifications.exists())


class PerformanceTests(AuthMixin, APITestCase):
    """§46: reasonable inference time and flat query counts. The time bound is
    deliberately loose because the test database is remote (Neon); the
    figures actually observed are recorded in the phase report."""

    TIME_BUDGET_SECONDS = 15.0

    def setUp(self):
        self.w = build_ai_world()

    def _timed(self, name, username):
        self._auth_as(username)
        started = time.perf_counter()
        response = self.client.get(reverse(name))
        elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['available'], response.data)
        return elapsed, response.data['inference_ms']

    def test_each_model_answers_within_the_budget(self):
        for name, username in (('ai-recommendations', 'studenthigh'),
                               ('ai-anomalies', 'sysadmin'), ('ai-engagement', 'sysadmin')):
            elapsed, inference_ms = self._timed(name, username)
            self.assertLess(elapsed, self.TIME_BUDGET_SECONDS, f'{name} took {elapsed:.1f}s')
            self.assertGreater(inference_ms, 0)

    def _count(self, name, username):
        self._auth_as(username)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse(name))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return len(ctx.captured_queries)

    def _add_records(self, n=6):
        for i in range(n):
            student = make_student(f'perf{i}', self.w.cs)
            p = make_participation(student=student, event=self.w.cs_tech_past)
            evidence_with_capture(participation=p, distance_m=20, accuracy_m=10, delay_seconds=5)

    def test_engagement_query_count_does_not_grow_with_students(self):
        before = self._count('ai-engagement', 'sysadmin')
        self._add_records()
        after = self._count('ai-engagement', 'sysadmin')
        self.assertEqual(before, after, f'engagement grew {before} -> {after}: N+1')

    def test_anomaly_query_count_does_not_grow_with_evidence(self):
        before = self._count('ai-anomalies', 'sysadmin')
        self._add_records()
        after = self._count('ai-anomalies', 'sysadmin')
        self.assertEqual(before, after, f'anomalies grew {before} -> {after}: N+1')
