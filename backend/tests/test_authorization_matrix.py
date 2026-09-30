"""
Phase 9 §5 — the role × endpoint authorization matrix, written out as data.

Each row is (url name, {role: expected status}). The expectation for a role
that is missing from a row is 200 (the endpoint lists something for them,
possibly nothing). Anonymous is always 401. Every collection endpoint in the
API appears here, so a new endpoint that forgets `IsAuthenticated` or a role
check breaks this test rather than shipping.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import AuthMixin, build_universe

ROLES = {'studenta': 'STUDENT', 'facultya': 'FACULTY', 'hoda': 'EVENT_COORDINATOR', 'sysadmin': 'ADMIN'}

# GET collection endpoints.
READ_MATRIX = [
    ('user-me', {}),
    ('event-list', {}),
    ('registration-list', {}),
    ('participation-list', {}),
    ('evidence-list', {}),
    ('attendance-list', {}),
    ('od-request-list', {}),
    ('achievement-list', {}),
    ('notification-list', {}),
    ('notification-unread-count', {}),
    ('activity-list', {}),
    ('dashboard', {}),
    ('analytics-overview', {}),
    ('analytics-participation', {}),
    ('analytics-events', {}),
    ('analytics-registrations', {}),
    ('analytics-attendance', {}),
    ('analytics-od', {}),
    ('analytics-achievements', {}),
    ('analytics-verification', {}),
    ('analytics-trends', {}),
    ('report-types', {}),
    ('ai-engagement', {}),
    ('ai-anomalies', {}),
    ('registration-request-list', {'STUDENT': 403, 'FACULTY': 403}),
    ('auditlog-list', {'STUDENT': 403, 'FACULTY': 403}),
    ('analytics-departments', {'STUDENT': 403, 'FACULTY': 403}),
    ('ai-recommendations', {'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 403}),
]

# Write endpoints that must refuse the wrong role outright at the view level
# (before any object is looked at). Body is minimal/invalid on purpose: a
# refused role must get 403, an allowed role gets a validation 400/404.
WRITE_MATRIX = [
    ('event-list', 'post', {'STUDENT': 403, 'FACULTY': 403, 'EVENT_COORDINATOR': 400, 'ADMIN': 400}),
    ('registration-list', 'post', {'STUDENT': 400, 'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 403}),
    ('participation-list', 'post', {'STUDENT': 400, 'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 403}),
    ('evidence-list', 'post', {'STUDENT': 400, 'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 403}),
    ('attendance-list', 'post', {'STUDENT': 403, 'FACULTY': 400, 'EVENT_COORDINATOR': 403, 'ADMIN': 403}),
    ('od-request-list', 'post', {'STUDENT': 403, 'FACULTY': 400, 'EVENT_COORDINATOR': 403, 'ADMIN': 403}),
    ('achievement-list', 'post', {'STUDENT': 403, 'FACULTY': 400, 'EVENT_COORDINATOR': 400, 'ADMIN': 400}),
    ('provision-event-coordinator', 'post', {'STUDENT': 403, 'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 400}),
    ('department-list', 'post', {'STUDENT': 403, 'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 400}),
    ('college-list', 'post', {'STUDENT': 403, 'FACULTY': 403, 'EVENT_COORDINATOR': 403, 'ADMIN': 400}),
]

# Endpoints that must not exist as writable at all.
NO_WRITE = [
    ('notification-list', 'post'), ('auditlog-list', 'post'), ('activity-list', 'post'),
    ('dashboard', 'post'), ('analytics-overview', 'post'), ('ai-engagement', 'post'),
    ('ai-anomalies', 'post'), ('ai-recommendations', 'post'), ('report-types', 'post'),
]


class AuthorizationMatrixTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()

    def test_anonymous_is_refused_everywhere(self):
        self._anon()
        for name, _ in READ_MATRIX:
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, name)
        for name, method, _ in WRITE_MATRIX:
            response = getattr(self.client, method)(reverse(name), {})
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, name)

    def test_read_matrix(self):
        for username, role in ROLES.items():
            self._auth_as(username)
            for name, exceptions in READ_MATRIX:
                expected = exceptions.get(role, status.HTTP_200_OK)
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, expected, f'{role} GET {name}: {response.data}')

    def test_write_matrix(self):
        for username, role in ROLES.items():
            self._auth_as(username)
            for name, method, expected_by_role in WRITE_MATRIX:
                response = getattr(self.client, method)(reverse(name), {})
                self.assertEqual(response.status_code, expected_by_role[role], f'{role} {method} {name}')

    def test_read_only_resources_reject_writes_for_every_role(self):
        for username in ROLES:
            self._auth_as(username)
            for name, method in NO_WRITE:
                response = getattr(self.client, method)(reverse(name), {})
                self.assertIn(response.status_code, (405, 403), f'{username} {method} {name}')

    def test_public_reference_data_is_read_only_for_anonymous(self):
        self._anon()
        self.assertEqual(self.client.get(reverse('department-list')).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get(reverse('college-list')).status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.post(reverse('department-list'), {'code': 'X', 'name': 'X'}).status_code, 401)
        self.assertEqual(self.client.get(reverse('health-check')).status_code, status.HTTP_200_OK)

    def test_student_and_faculty_get_empty_or_own_lists_never_other_peoples(self):
        """Where a role is allowed to call a list, the list must contain only
        rows inside their scope — asserted by ids, not by count."""
        self._auth_as('studenta')
        for name, mine in (
            ('registration-list', self.u.a.registration.id), ('participation-list', self.u.a.participation.id),
            ('evidence-list', self.u.a.evidence.id), ('attendance-list', self.u.a.attendance.id),
            ('od-request-list', self.u.a.od.id), ('achievement-list', self.u.a.achievement.id),
            ('notification-list', self.u.a.notification.id),
        ):
            ids = {row['id'] for row in self.client.get(reverse(name)).data['results']}
            self.assertEqual(ids, {mine}, name)
        self._auth_as('facultya')
        ids = {row['id'] for row in self.client.get(reverse('evidence-list')).data['results']}
        self.assertEqual(ids, {self.u.a.evidence.id})
        # Faculty now have a registration scope (their own department's
        # events), so the assertion is that it is exactly their department —
        # never another's, which is what this matrix is really guarding.
        ids = {row['id'] for row in self.client.get(reverse('registration-list')).data['results']}
        self.assertEqual(ids, {self.u.a.registration.id})
        self.assertNotIn(self.u.b.registration.id, ids)
