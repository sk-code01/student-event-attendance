from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import Evidence, EvidenceVerification

from .helpers import (
    make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_participation, make_student,
    make_submitted_evidence, make_todays_published_event,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class HodOverrideTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.student = make_student('ostudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
        )
        self.participation = make_participation(student=self.student, event=self.event)
        self.evidence, self.version = make_submitted_evidence(participation=self.participation)

        self.override_url = reverse('evidence-override', args=[self.evidence.id])

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def _faculty_reject(self):
        self._auth_as('facultycs')
        response = self.client.post(reverse('evidence-reject', args=[self.evidence.id]), {'reason': 'blurry photo'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_override_requires_an_existing_faculty_decision(self):
        self._auth_as('hodcs')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'looks fine to me'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_coordinator_can_override_faculty_rejection_to_verified(self):
        self._faculty_reject()
        self._auth_as('hodcs')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'reviewed personally, valid'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Evidence.Status.VERIFIED)

        version_data = response.data['versions'][0]
        decisions = [v['decision'] for v in version_data['verifications']]
        self.assertEqual(decisions, ['REJECTED', 'VERIFIED'])
        self.assertFalse(version_data['verifications'][0]['is_event_coordinator_override'])
        self.assertTrue(version_data['verifications'][1]['is_event_coordinator_override'])

    def test_override_without_reason_is_rejected(self):
        self._faculty_reject()
        self._auth_as('hodcs')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': ''})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_coordinator_from_other_department_cannot_override(self):
        self._faculty_reject()
        self._auth_as('hodec')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'trying anyway'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_student_cannot_call_override_endpoint(self):
        self._faculty_reject()
        self._auth_as('ostudent')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'trying anyway'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_cannot_override_via_event_coordinator_endpoint(self):
        self._faculty_reject()
        self._auth_as('facultycs')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'trying anyway'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_override_system_wide(self):
        self._faculty_reject()
        make_admin('siteadmin3')
        self._auth_as('siteadmin3')
        response = self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'system-wide admin review'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_event_coordinator_delete_of_faculty_history_is_not_possible_through_the_api(self):
        """There is no endpoint that deletes an EvidenceVerification row at
        all — overriding always creates a new row."""
        self._faculty_reject()
        self._auth_as('hodcs')
        self.client.post(self.override_url, {'decision': 'VERIFIED', 'reason': 'reviewed'})
        self.assertEqual(EvidenceVerification.objects.filter(evidence_version=self.version).count(), 2)
