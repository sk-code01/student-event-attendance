from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import Evidence

from .helpers import (
    make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_participation, make_student,
    make_submitted_evidence, make_todays_published_event,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class FacultyVerificationTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.student = make_student('vstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
        )
        self.participation = make_participation(student=self.student, event=self.event)
        self.evidence, self.version = make_submitted_evidence(participation=self.participation)

        self.detail_url = reverse('evidence-detail', args=[self.evidence.id])
        self.verify_url = reverse('evidence-verify', args=[self.evidence.id])
        self.reject_url = reverse('evidence-reject', args=[self.evidence.id])
        self.resubmission_url = reverse('evidence-request-resubmission', args=[self.evidence.id])

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_faculty_can_view_own_department_evidence(self):
        self._auth_as('facultycs')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['student']['username'], 'vstudent')
        self.assertEqual(len(response.data['versions'][0]['captures']), 1)

    def test_viewing_transitions_submitted_to_under_review(self):
        self._auth_as('facultycs')
        self.assertEqual(Evidence.objects.get(pk=self.evidence.id).status, Evidence.Status.SUBMITTED)
        self.client.get(self.detail_url)
        self.assertEqual(Evidence.objects.get(pk=self.evidence.id).status, Evidence.Status.UNDER_REVIEW)

    def test_faculty_from_other_department_cannot_view_evidence(self):
        self._auth_as('facultyec')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_faculty_from_other_department_cannot_verify(self):
        self._auth_as('facultyec')
        response = self.client.post(self.verify_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_verify_succeeds_with_optional_reason(self):
        self._auth_as('facultycs')
        response = self.client.post(self.verify_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Evidence.Status.VERIFIED)
        self.assertEqual(response.data['versions'][0]['verifications'][0]['decision'], 'VERIFIED')

    def test_reject_without_reason_is_rejected(self):
        self._auth_as('facultycs')
        response = self.client.post(self.reject_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reject_with_reason_succeeds(self):
        self._auth_as('facultycs')
        response = self.client.post(self.reject_url, {'reason': 'Image does not match venue'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Evidence.Status.REJECTED)

    def test_request_resubmission_without_reason_is_rejected(self):
        self._auth_as('facultycs')
        response = self.client.post(self.resubmission_url, {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_request_resubmission_with_reason_succeeds(self):
        self._auth_as('facultycs')
        response = self.client.post(self.resubmission_url, {'reason': 'Please retake a clearer photo'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Evidence.Status.RESUBMISSION_REQUIRED)

    def test_cannot_decide_twice_on_same_version(self):
        self._auth_as('facultycs')
        self.client.post(self.verify_url)
        second = self.client.post(self.verify_url)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_verify_own_evidence(self):
        self._auth_as('vstudent')
        response = self.client.post(self.verify_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_reject_own_evidence(self):
        self._auth_as('vstudent')
        response = self.client.post(self.reject_url, {'reason': 'self reject'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_view_but_cannot_call_faculty_verify_action(self):
        """Admin can inspect everything, but does not get to impersonate a
        Faculty decision through the Faculty-only decision actions —
        superuser is the only bypass, and admin role accounts are not
        superusers by default."""
        make_admin('siteadmin2')
        self._auth_as('siteadmin2')
        view_response = self.client.get(self.detail_url)
        self.assertEqual(view_response.status_code, status.HTTP_200_OK)

        verify_response = self.client.post(self.verify_url)
        self.assertEqual(verify_response.status_code, status.HTTP_403_FORBIDDEN)
