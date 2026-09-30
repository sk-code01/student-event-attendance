"""
Dashboard scope and correctness.

The property that matters: each role's counts are computed from its own
scope server-side, so an out-of-scope record is never counted, never
serialized, and never sent to Angular to be filtered there.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.od.models import ODRequest
from apps.registrations.models import Registration

from apps.notifications.tests.helpers import (
    AuthMixin,
    make_admin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
    make_verified_participation,
)


def card(payload, key):
    """The value of one card, or None when the role is not shown that card."""
    for entry in payload['cards']:
        if entry['key'] == key:
            return entry['value']
    return None


class DashboardScopeTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')

        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.admin = make_admin('sysadmin')

        self.student_cs = make_student('studentcs', self.cs)
        self.student_other = make_student('studentother', self.cs)
        self.student_ec = make_student('studentec', self.ec)

        self.event_cs = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs, title='CS Event',
        )
        self.event_ec = make_todays_published_event(
            created_by=self.event_coordinator_ec, college=self.college, department=self.ec, title='EC Event',
        )

        # One CS attendance pending, one EC attendance pending.
        self.participation_cs = make_verified_participation(
            student=self.student_cs, event=self.event_cs, reviewer=self.faculty_cs,
        )
        Attendance.objects.create(participation=self.participation_cs, requested_by=self.faculty_cs)

        participation_ec = make_verified_participation(
            student=self.student_ec, event=self.event_ec, reviewer=self.faculty_ec,
        )
        Attendance.objects.create(participation=participation_ec, requested_by=self.faculty_ec)

        self.url = reverse('dashboard')

    def _get(self, username):
        self._auth_as(username)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data

    # --- student ------------------------------------------------------------

    def test_student_sees_only_their_own_counts(self):
        payload = self._get('studentcs')
        self.assertEqual(payload['role'], 'STUDENT')
        self.assertEqual(card(payload, 'participations'), 1)
        self.assertEqual(card(payload, 'attendance_pending'), 1)

        other = self._get('studentother')
        self.assertEqual(card(other, 'participations'), 0)
        self.assertEqual(card(other, 'attendance_pending'), 0)

    def test_student_dashboard_exposes_no_admin_cards(self):
        payload = self._get('studentcs')
        keys = {entry['key'] for entry in payload['cards']}
        self.assertNotIn('total_users', keys)
        self.assertNotIn('departments', keys)

    def test_student_with_no_data_gets_zeros_not_errors(self):
        empty = make_student('emptystudent', self.cs)
        empty.set_password('StrongPass123!')
        empty.save()
        payload = self._get('emptystudent')
        for entry in payload['cards']:
            self.assertIsInstance(entry['value'], int)
        self.assertEqual(card(payload, 'achievements'), 0)
        self.assertEqual(payload['recent_activity'], [])

    # --- faculty ------------------------------------------------------------

    def test_faculty_counts_are_department_scoped(self):
        cs = self._get('facultycs')
        self.assertEqual(cs['role'], 'FACULTY')
        self.assertEqual(card(cs, 'pending_attendance'), 1)

        ec = self._get('facultyec')
        self.assertEqual(card(ec, 'pending_attendance'), 1)  # its own, not CS's

    def test_faculty_sees_no_event_coordinator_or_admin_cards(self):
        payload = self._get('facultycs')
        keys = {entry['key'] for entry in payload['cards']}
        self.assertNotIn('pending_registrations', keys)
        self.assertNotIn('total_users', keys)

    # --- event_coordinator ----------------------------------------------------------------

    def test_event_coordinator_counts_are_department_scoped(self):
        cs = self._get('hodcs')
        self.assertEqual(cs['role'], 'EVENT_COORDINATOR')
        self.assertEqual(card(cs, 'pending_attendance'), 1)
        self.assertEqual(card(cs, 'department_events'), 1)

    def test_event_coordinator_does_not_see_the_other_departments_pending_work(self):
        """Both departments have exactly one pending attendance; each Event Coordinator must
        report 1, not 2."""
        self.assertEqual(card(self._get('hodcs'), 'pending_attendance'), 1)
        self.assertEqual(card(self._get('hodec'), 'pending_attendance'), 1)
        self.assertEqual(Attendance.objects.count(), 2)

    def test_event_coordinator_sees_no_admin_cards(self):
        keys = {entry['key'] for entry in self._get('hodcs')['cards']}
        self.assertNotIn('total_users', keys)
        self.assertNotIn('colleges', keys)

    # --- admin --------------------------------------------------------------

    def test_admin_sees_system_wide_totals(self):
        payload = self._get('sysadmin')
        self.assertEqual(payload['role'], 'ADMIN')
        self.assertEqual(card(payload, 'pending_attendance'), 2)  # both departments
        self.assertEqual(card(payload, 'events'), 2)
        self.assertGreaterEqual(card(payload, 'total_users'), 8)

    # --- shared -------------------------------------------------------------

    def test_unauthenticated_access_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_every_card_route_is_an_internal_path(self):
        for username in ('studentcs', 'facultycs', 'hodcs', 'sysadmin'):
            for entry in self._get(username)['cards']:
                self.assertTrue(entry['route'].startswith('/'), entry)
                self.assertFalse(entry['route'].startswith('//'), entry)


class DashboardCorrectnessTests(AuthMixin, APITestCase):
    """Aggregation correctness against a known fixture."""

    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('countstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.url = reverse('dashboard')

    def test_pending_verification_counts_only_undecided_evidence(self):
        pending_participation = make_participation(student=self.student, event=self.event)
        make_submitted_evidence(participation=pending_participation)

        self._auth_as('countstudent')
        payload = self.client.get(self.url).data
        self.assertEqual(card(payload, 'pending_verification'), 1)
        self.assertEqual(card(payload, 'verified_evidence'), 0)

    def test_approved_and_pending_attendance_are_counted_separately(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        Attendance.objects.create(
            participation=participation, requested_by=self.faculty,
            status=Attendance.Status.PENDING,
        )
        self._auth_as('countstudent')
        payload = self.client.get(self.url).data
        self.assertEqual(card(payload, 'attendance_pending'), 1)
        self.assertEqual(card(payload, 'attendance_approved'), 0)

    def test_only_approved_achievements_are_counted_for_a_student(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        Achievement.objects.create(
            participation=participation, created_by=self.faculty, title='Pending one',
            achievement_type='Competition', achievement_date=self.event.event_date,
            status=Achievement.Status.PENDING_APPROVAL,
        )
        self._auth_as('countstudent')
        self.assertEqual(card(self.client.get(self.url).data, 'achievements'), 0)

    def test_registered_events_counts_live_registrations_only(self):
        Registration.objects.create(student=self.student, event=self.event)
        self._auth_as('countstudent')
        self.assertEqual(card(self.client.get(self.url).data, 'registered_events'), 1)


class DashboardQueryBudgetTests(AuthMixin, APITestCase):
    """Guards against N+1: the dashboard issues a fixed number of queries that
    does not grow with the amount of data, because every count is an aggregate
    rather than a Python loop over related rows."""

    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('budgetstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.url = reverse('dashboard')

    def _count_queries(self, username):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._auth_as(username)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return len(ctx.captured_queries)

    def test_student_dashboard_query_count_does_not_grow_with_data(self):
        empty = self._count_queries('budgetstudent')

        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        Attendance.objects.create(participation=participation, requested_by=self.faculty)
        ODRequest.objects.create(
            participation=participation, requested_by=self.faculty, reason='Fest',
        )
        Registration.objects.create(
            student=self.student,
            event=make_todays_published_event(
                created_by=self.event_coordinator, college=self.college, department=self.cs, title='Another',
            ),
        )
        populated = self._count_queries('budgetstudent')

        self.assertEqual(
            empty, populated,
            f'Dashboard query count grew from {empty} to {populated} when data was added, '
            f'which indicates an N+1.',
        )

    def test_event_coordinator_dashboard_query_count_does_not_grow_with_data(self):
        empty = self._count_queries('hodcs')

        for index in range(3):
            student = make_student(f'bulkstudent{index}', self.cs)
            participation = make_verified_participation(
                student=student, event=self.event, reviewer=self.faculty,
            )
            Attendance.objects.create(participation=participation, requested_by=self.faculty)
        populated = self._count_queries('hodcs')

        self.assertEqual(
            empty, populated,
            f'Event Coordinator dashboard query count grew from {empty} to {populated}.',
        )
