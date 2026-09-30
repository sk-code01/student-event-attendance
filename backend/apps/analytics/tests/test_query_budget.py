"""
Query-budget tests (§42).

These endpoints aggregate, so their query count must not grow with the number
of rows. Each test measures an empty-ish scope, adds a batch of real records,
and asserts the count is unchanged — which is exactly what would break if
someone replaced a conditional aggregate with a loop like
``for event in events: event.registrations.count()``.
"""

from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.registrations.models import Registration

from .helpers import (
    AuthMixin,
    build_world,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
)


class QueryBudgetTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_world()

    def _count(self, name, params=None):
        self._auth_as('hodcs')
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(reverse(name), params or {})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return len(ctx.captured_queries)

    def _add_records(self, count=6):
        """Adds real, fully-populated records inside the CS scope."""
        for index in range(count):
            student = make_student(f'budget{index}', self.w.cs)
            event = make_todays_published_event(
                created_by=self.w.event_coordinator_cs, college=self.w.college, department=self.w.cs,
                title=f'Budget Event {index}',
            )
            participation = make_participation(student=student, event=event)
            make_submitted_evidence(participation=participation)
            Attendance.objects.create(participation=participation, requested_by=self.w.faculty_cs)
            Registration.objects.create(student=student, event=self.w.cs_event)

    def test_overview_query_count_is_flat(self):
        before = self._count('analytics-overview')
        self._add_records()
        after = self._count('analytics-overview')
        self.assertEqual(before, after, f'overview grew {before} -> {after}; likely an N+1')

    def test_events_query_count_is_flat(self):
        """The per-event breakdown is the most N+1-prone endpoint: it reports
        registration and participation counts for every event."""
        before = self._count('analytics-events')
        self._add_records()
        after = self._count('analytics-events')
        self.assertEqual(before, after, f'events grew {before} -> {after}; likely an N+1')

    def test_participation_query_count_is_flat(self):
        before = self._count('analytics-participation')
        self._add_records()
        after = self._count('analytics-participation')
        self.assertEqual(before, after, f'participation grew {before} -> {after}')

    def test_verification_query_count_is_flat(self):
        before = self._count('analytics-verification')
        self._add_records()
        after = self._count('analytics-verification')
        self.assertEqual(before, after, f'verification grew {before} -> {after}')

    def test_trends_query_count_is_flat(self):
        before = self._count('analytics-trends', {'period': 'monthly'})
        self._add_records()
        after = self._count('analytics-trends', {'period': 'monthly'})
        self.assertEqual(before, after, f'trends grew {before} -> {after}')

    def test_departments_query_count_is_flat(self):
        self._auth_as('sysadmin')
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('analytics-departments'))
        before = len(ctx.captured_queries)

        self._add_records()

        self._auth_as('sysadmin')
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(reverse('analytics-departments'))
        after = len(ctx.captured_queries)
        self.assertEqual(before, after, f'departments grew {before} -> {after}')
