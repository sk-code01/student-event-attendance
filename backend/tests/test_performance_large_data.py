"""
Phase 9 §23/§24 — query budgets and a large synthetic dataset, built in the
test database only (never in Neon's dev database).

The assertion that matters is that the number of queries an endpoint issues
does not change when the data grows: that is exactly what an N+1 breaks.
Wall-clock numbers are recorded for the report but bounded loosely, because
the test database is a remote Neon instance.
"""

import time
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.events.models import Event
from apps.notifications.models import Notification
from apps.participation.models import Participation
from apps.registrations.models import Registration
from apps.verification.models import Evidence, EvidenceVersion

from .helpers import DEFAULT_PASSWORD, AuthMixin, build_universe

STUDENTS = 200
EVENTS = 40
REGISTRATIONS_PER_STUDENT = 8
PARTICIPATIONS = 600
NOTIFICATIONS = 1500
TIME_BUDGET_SECONDS = 60.0

TIMINGS = {}


def grow(u):
    """Bulk-creates the large dataset in department A."""
    hashed = make_password(DEFAULT_PASSWORD)
    students = User.objects.bulk_create([
        User(username=f'bulk{i:04d}', email=f'bulk{i:04d}@example.com', role=User.Role.STUDENT,
             department=u.a.department, is_active=True, password=hashed)
        for i in range(STUDENTS)
    ])
    today = timezone.localdate()
    events = Event.objects.bulk_create([
        Event(title=f'Bulk Event {i}', description='', event_date=today - timedelta(days=i % 30 + 1),
              venue='Hall', category=('Technical', 'Cultural', 'Sports', 'Workshop')[i % 4],
              conducting_college=u.college, department=u.a.department, created_by=u.a.event_coordinator,
              status=Event.Status.COMPLETED, registration_start_date=today - timedelta(days=i % 30 + 10),
              registration_end_date=today - timedelta(days=i % 30 + 2))
        for i in range(EVENTS)
    ])
    registrations = Registration.objects.bulk_create([
        Registration(student=student, event=events[(i * 7 + j) % EVENTS])
        for i, student in enumerate(students) for j in range(REGISTRATIONS_PER_STUDENT)
    ])
    participations = Participation.objects.bulk_create([
        Participation(registration=registration, student=registration.student, event=registration.event,
                      status=Participation.Status.SUBMITTED, submitted_at=timezone.now())
        for registration in registrations[:PARTICIPATIONS]
    ])
    evidence = Evidence.objects.bulk_create([
        Evidence(participation=p, status=(Evidence.Status.VERIFIED, Evidence.Status.SUBMITTED,
                                          Evidence.Status.REJECTED)[i % 3])
        for i, p in enumerate(participations)
    ])
    versions = EvidenceVersion.objects.bulk_create([
        EvidenceVersion(evidence=e, version_number=1, submitted_by=e.participation.student, submitted_at=timezone.now())
        for e in evidence
    ])
    for e, v in zip(evidence, versions):
        e.current_version = v
    Evidence.objects.bulk_update(evidence, ['current_version'])
    Notification.objects.bulk_create([
        Notification(recipient=students[i % STUDENTS], notification_type=Notification.Type.EVENT_PUBLISHED,
                     title=f'Bulk {i}', message='x', action_route='/student/events')
        for i in range(NOTIFICATIONS)
    ])
    # Open events for the recommendation candidates.
    Event.objects.bulk_create([
        Event(title=f'Bulk Open {i}', description='', event_date=today + timedelta(days=10 + i), venue='Hall',
              category='Technical', conducting_college=u.college, department=u.a.department,
              created_by=u.a.event_coordinator,
              status=Event.Status.PUBLISHED, registration_start_date=today - timedelta(days=1),
              registration_end_date=today + timedelta(days=5))
        for i in range(15)
    ])


class LargeDataTests(AuthMixin, APITestCase):
    """One dataset build per class (setUpTestData), reused by every test."""

    @classmethod
    def setUpTestData(cls):
        cls.u = build_universe()
        # Register the fixture student for a few bulk events so the student
        # views have something to paginate.
        cls.small_counts = {}

    _tokens = {}

    def _count(self, name, username, params=None):
        # Log in once per user: dozens of logins in one test would trip the
        # 10/min auth throttle, which is the throttle test's job, not this one's.
        if username not in self._tokens:
            self._tokens[username] = self._auth_as(username)['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self._tokens[username]}')
        with CaptureQueriesContext(connection) as ctx:
            started = time.perf_counter()
            response = self.client.get(reverse(name) if isinstance(name, str) else name, params or {})
            elapsed = time.perf_counter() - started
        self.assertEqual(response.status_code, status.HTTP_200_OK, getattr(response, 'data', None))
        return len(ctx.captured_queries), elapsed, response

    ENDPOINTS = [
        ('event-list', 'studenta', None), ('event-list', 'sysadmin', None),
        ('registration-list', 'sysadmin', None), ('participation-list', 'hoda', None),
        ('evidence-list', 'facultya', None), ('attendance-list', 'sysadmin', None),
        ('achievement-list', 'sysadmin', None), ('notification-list', 'studenta', None),
        ('auditlog-list', 'sysadmin', None), ('dashboard', 'sysadmin', None), ('dashboard', 'hoda', None),
        ('dashboard', 'studenta', None), ('analytics-overview', 'sysadmin', None),
        ('analytics-participation', 'hoda', None), ('analytics-events', 'sysadmin', None),
        ('analytics-trends', 'sysadmin', {'period': 'monthly'}), ('analytics-departments', 'sysadmin', None),
        ('ai-engagement', 'sysadmin', None), ('ai-anomalies', 'sysadmin', None),
        ('ai-recommendations', 'studenta', None),
    ]

    def test_query_counts_do_not_grow_with_the_dataset(self):
        self._tokens.clear()
        before = {(name, user): self._count(name, user, params)[0] for name, user, params in self.ENDPOINTS}
        grow(self.u)
        after = {}
        for name, user, params in self.ENDPOINTS:
            queries, elapsed, _ = self._count(name, user, params)
            after[(name, user)] = queries
            TIMINGS[f'{name} as {user}'] = round(elapsed, 2)
            self.assertLess(elapsed, TIME_BUDGET_SECONDS, f'{name} as {user} took {elapsed:.1f}s')
        # A handful of constant extra statements is legitimate (Django skips a
        # `__in=[]` query entirely on an empty fixture, then issues it once the
        # rows exist); an N+1 adds one query per row and is what this catches.
        grew = {k: (before[k], after[k]) for k in before if after[k] > before[k] + 3}
        self.assertEqual(grew, {}, f'query count grew with data (N+1): {grew}')

    def test_reports_stay_flat_and_complete_on_the_large_dataset(self):
        grow(self.u)
        self._auth_as('sysadmin')
        for report in ('student-participation', 'event', 'registration', 'verification', 'department', 'system'):
            with CaptureQueriesContext(connection) as ctx:
                started = time.perf_counter()
                response = self.client.get(reverse('report-export', args=[report]), {'file_format': 'csv'})
                elapsed = time.perf_counter() - started
            self.assertEqual(response.status_code, status.HTTP_200_OK, report)
            self.assertLess(len(ctx.captured_queries), 40, f'{report}: {len(ctx.captured_queries)} queries')
            self.assertLess(elapsed, TIME_BUDGET_SECONDS)
            TIMINGS[f'report {report} csv'] = round(elapsed, 2)
        response = self.client.get(reverse('report-export', args=['student-participation']), {'file_format': 'csv'})
        rows = response.content.decode('utf-8-sig').count('\r\n') - 1
        self.assertGreaterEqual(rows, PARTICIPATIONS)

    def test_ai_remains_available_and_scoped_on_the_large_dataset(self):
        grow(self.u)
        self._auth_as('sysadmin')
        engagement = self.client.get(reverse('ai-engagement')).data
        self.assertTrue(engagement['available'], engagement)
        self.assertGreaterEqual(engagement['scoped_students'], STUDENTS)
        self.assertEqual(engagement['label_order'], ['LOW', 'MODERATE', 'HIGH'])
        anomalies = self.client.get(reverse('ai-anomalies'), {'limit': 500}).data
        self.assertTrue(anomalies['available'], anomalies)
        self.assertGreaterEqual(anomalies['population']['n_samples'], PARTICIPATIONS)
        self._auth_as('hodb')
        self.assertEqual(self.client.get(reverse('ai-engagement')).data['scoped_students'], 1)
        self._auth_as('studenta')
        recs = self.client.get(reverse('ai-recommendations')).data
        self.assertTrue(recs['available'])
        self.assertLessEqual(len(recs['results']), 10)
        TIMINGS['ai inference_ms engagement'] = engagement['inference_ms']
        TIMINGS['ai inference_ms anomalies'] = anomalies['inference_ms']
        TIMINGS['ai inference_ms recommendations'] = recs['inference_ms']

    def test_pagination_bounds_every_large_list(self):
        grow(self.u)
        self._auth_as('sysadmin')
        for name in ('registration-list', 'participation-list', 'evidence-list', 'event-list', 'auditlog-list'):
            data = self.client.get(reverse(name)).data
            self.assertLessEqual(len(data['results']), 20, name)
            self.assertIn('count', data)
        self._auth_as('bulk0000')
        data = self.client.get(reverse('notification-list')).data
        self.assertLessEqual(len(data['results']), 20)
        self.assertGreater(data['count'], 0)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        if TIMINGS:
            print('\nPhase 9 large-data timings (seconds unless noted):')
            for key, value in TIMINGS.items():
                print(f'  {key}: {value}')
