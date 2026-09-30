"""
Audit and activity presentation.

Three properties matter here:
  * `/activity/` is always the caller's own records — no role sees another
    user's activity feed through it, Admin included.
  * `/audit/` is Event Coordinator/Admin only, and an Event Coordinator is scoped to their department.
  * Nothing sensitive is exposed, because AuditLog never stored anything
    sensitive in the first place.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog

from apps.notifications.tests.helpers import (
    AuthMixin,
    make_admin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
)


class ActivityFeedTests(AuthMixin, APITestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.admin = make_admin('sysadmin')
        self.student_a = make_student('studenta', self.cs)
        self.student_b = make_student('studentb', self.cs)

        AuditLog.record(actor=self.student_a, action='EVENT_REGISTERED', description='A registered.')
        AuditLog.record(actor=self.student_b, action='EVENT_REGISTERED', description='B registered.')
        self.url = reverse('activity-list')

    def test_activity_returns_only_the_callers_own_records(self):
        self._auth_as('studenta')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        descriptions = [row['description'] for row in response.data['results']]
        self.assertEqual(descriptions, ['A registered.'])

    def test_admin_activity_is_also_only_their_own(self):
        """Admin oversight belongs to /audit/. The personal feed stays personal
        for every role."""
        self._auth_as('sysadmin')
        self.assertEqual(self.client.get(self.url).data['results'], [])

    def test_activity_requires_authentication(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_activity_can_be_filtered_by_action(self):
        AuditLog.record(actor=self.student_a, action='REGISTRATION_CANCELLED', description='A cancelled.')
        self._auth_as('studenta')
        response = self.client.get(self.url, {'action': 'REGISTRATION_CANCELLED'})
        self.assertEqual([row['description'] for row in response.data['results']], ['A cancelled.'])


class AuditTrailTests(AuthMixin, APITestCase):
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

        AuditLog.record(actor=self.faculty_cs, action='EVIDENCE_VERIFIED', description='CS verification.')
        AuditLog.record(actor=self.faculty_ec, action='EVIDENCE_VERIFIED', description='EC verification.')
        AuditLog.record(actor=None, action='EVENT_UPDATED', description='System action.')
        self.url = reverse('auditlog-list')

    # --- access control -----------------------------------------------------

    def test_student_is_refused(self):
        self._auth_as('studentcs')
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_is_refused(self):
        self._auth_as('facultycs')
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_admin_sees_system_wide_records(self):
        self._auth_as('sysadmin')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        descriptions = {row['description'] for row in response.data['results']}
        self.assertIn('CS verification.', descriptions)
        self.assertIn('EC verification.', descriptions)
        self.assertIn('System action.', descriptions)

    # --- department scoping -------------------------------------------------

    def test_event_coordinator_sees_only_their_own_departments_records(self):
        self._auth_as('hodcs')
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        descriptions = {row['description'] for row in response.data['results']}
        self.assertIn('CS verification.', descriptions)
        self.assertNotIn('EC verification.', descriptions)

    def test_event_coordinator_does_not_see_system_actor_records_of_other_departments(self):
        self._auth_as('hodec')
        descriptions = {row['description'] for row in self.client.get(self.url).data['results']}
        self.assertIn('EC verification.', descriptions)
        self.assertNotIn('CS verification.', descriptions)

    # --- filtering ----------------------------------------------------------

    def test_filter_by_action(self):
        self._auth_as('sysadmin')
        response = self.client.get(self.url, {'action': 'EVENT_UPDATED'})
        self.assertEqual([row['description'] for row in response.data['results']], ['System action.'])

    def test_filter_by_actor(self):
        self._auth_as('sysadmin')
        response = self.client.get(self.url, {'actor': self.faculty_cs.id})
        self.assertEqual([row['description'] for row in response.data['results']], ['CS verification.'])

    def test_filter_by_description_search(self):
        self._auth_as('sysadmin')
        response = self.client.get(self.url, {'search': 'EC verif'})
        self.assertEqual([row['description'] for row in response.data['results']], ['EC verification.'])

    def test_results_are_paginated_and_newest_first(self):
        for index in range(25):
            AuditLog.record(actor=self.admin, action='EVENT_UPDATED', description=f'Bulk {index}.')
        self._auth_as('sysadmin')
        response = self.client.get(self.url)
        self.assertEqual(len(response.data['results']), 20)
        self.assertIsNotNone(response.data['next'])
        self.assertEqual(response.data['results'][0]['description'], 'Bulk 24.')

    # --- shape / safety -----------------------------------------------------

    def test_a_system_action_has_a_null_actor_rather_than_failing(self):
        self._auth_as('sysadmin')
        rows = self.client.get(self.url, {'action': 'EVENT_UPDATED'}).data['results']
        self.assertIsNone(rows[0]['actor'])

    def test_serializer_exposes_no_unexpected_fields(self):
        self._auth_as('sysadmin')
        row = self.client.get(self.url).data['results'][0]
        self.assertEqual(set(row.keys()), {'id', 'actor', 'action', 'description', 'created_at'})

    def test_audit_is_read_only(self):
        self._auth_as('sysadmin')
        response = self.client.post(self.url, {'action': 'FORGED', 'description': 'injected'})
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertFalse(AuditLog.objects.filter(action='FORGED').exists())
