"""
OD request workflow: same effective-verification eligibility rules as
attendance, same Faculty-requests/Event Coordinator-decides authority split, but an entirely
separate record. The independence of the two workflows has its own test file
(test_independence.py).
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.od.models import ODRequest
from apps.verification.models import EvidenceVerification

from .helpers import (
    AuthMixin,
    make_admin,
    make_college,
    make_decided_participation,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
    make_verified_participation,
)

Decision = EvidenceVerification.Decision


class ODEligibilityTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.url = reverse('od-request-list')

    def _request_for(self, participation):
        self._auth_as('facultycs')
        return self.client.post(self.url, {'participation': participation.id, 'reason': 'Representing the college'})

    def test_verified_participation_is_eligible(self):
        student = make_student('odelig1', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        response = self._request_for(participation)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], ODRequest.Status.PENDING)
        self.assertEqual(response.data['reason'], 'Representing the college')

    def test_participation_without_evidence_is_not_eligible(self):
        student = make_student('odelig2', self.cs)
        participation = make_participation(student=student, event=self.event)
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_submitted_but_undecided_evidence_is_not_eligible(self):
        student = make_student('odelig3', self.cs)
        participation = make_participation(student=student, event=self.event)
        make_submitted_evidence(participation=participation)
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_rejected_evidence_is_not_eligible(self):
        student = make_student('odelig4', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.REJECTED,
        )
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_resubmission_required_evidence_is_not_eligible(self):
        student = make_student('odelig5', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.RESUBMISSION_REQUIRED,
        )
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_rejected_but_event_coordinator_override_verified_is_eligible(self):
        student = make_student('odelig6', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.REJECTED,
            override_by=self.event_coordinator, override_decision=Decision.VERIFIED,
        )
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_201_CREATED)

    def test_faculty_verified_but_event_coordinator_override_rejected_is_not_eligible(self):
        student = make_student('odelig7', self.cs)
        participation = make_decided_participation(
            student=student, event=self.event, reviewer=self.faculty, decision=Decision.VERIFIED,
            override_by=self.event_coordinator, override_decision=Decision.REJECTED,
        )
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ODRequest.objects.exists())

    def test_duplicate_od_request_for_same_participation_is_rejected(self):
        student = make_student('odelig8', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        self.assertEqual(self._request_for(participation).status_code, status.HTTP_201_CREATED)
        second = self.client.post(self.url, {'participation': participation.id, 'reason': 'again'})
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ODRequest.objects.filter(participation=participation).count(), 1)

    def test_request_without_a_reason_is_rejected(self):
        student = make_student('odelig9', self.cs)
        participation = make_verified_participation(student=student, event=self.event, reviewer=self.faculty)
        self._auth_as('facultycs')
        response = self.client.post(self.url, {'participation': participation.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ODRequest.objects.exists())


class ODWorkflowTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.admin = make_admin('sysadmin')
        self.student = make_student('odstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self.list_url = reverse('od-request-list')

    def _request_od(self):
        self._auth_as('facultycs')
        response = self.client.post(
            self.list_url, {'participation': self.participation.id, 'reason': 'Inter-college fest'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return ODRequest.objects.get(pk=response.data['id'])

    def test_faculty_can_request_od_and_it_is_audit_logged(self):
        od_request = self._request_od()
        self.assertEqual(od_request.status, ODRequest.Status.PENDING)
        self.assertEqual(od_request.requested_by_id, self.faculty.id)
        self.assertTrue(AuditLog.objects.filter(action='OD_REQUESTED', actor=self.faculty).exists())

    def test_student_cannot_request_od(self):
        self._auth_as('odstudent')
        response = self.client.post(self.list_url, {'participation': self.participation.id, 'reason': 'me'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_coordinator_can_approve_od(self):
        od_request = self._request_od()
        self._auth_as('hodcs')
        response = self.client.post(reverse('od-request-approve', args=[od_request.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], ODRequest.Status.APPROVED)
        self.assertEqual(response.data['reviewed_by']['username'], 'hodcs')
        self.assertTrue(AuditLog.objects.filter(action='OD_APPROVED').exists())

    def test_faculty_cannot_approve_od(self):
        od_request = self._request_od()
        response = self.client.post(reverse('od-request-approve', args=[od_request.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(ODRequest.objects.get(pk=od_request.id).status, ODRequest.Status.PENDING)

    def test_student_cannot_approve_their_own_od(self):
        od_request = self._request_od()
        self._auth_as('odstudent')
        response = self.client.post(reverse('od-request-approve', args=[od_request.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_od_reject_requires_a_reason(self):
        od_request = self._request_od()
        self._auth_as('hodcs')
        self.assertEqual(
            self.client.post(reverse('od-request-reject', args=[od_request.id]), {}).status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_event_coordinator_can_reject_od_with_a_reason(self):
        od_request = self._request_od()
        self._auth_as('hodcs')
        response = self.client.post(
            reverse('od-request-reject', args=[od_request.id]), {'reason': 'Not an approved category'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], ODRequest.Status.REJECTED)
        self.assertEqual(response.data['rejection_reason'], 'Not an approved category')
        self.assertTrue(AuditLog.objects.filter(action='OD_REJECTED').exists())

    def test_a_decided_od_request_is_final(self):
        od_request = self._request_od()
        self._auth_as('hodcs')
        self.client.post(reverse('od-request-reject', args=[od_request.id]), {'reason': 'no'})
        response = self.client.post(reverse('od-request-approve', args=[od_request.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(ODRequest.objects.get(pk=od_request.id).status, ODRequest.Status.REJECTED)

    def test_student_can_read_their_own_od_status_and_reason(self):
        od_request = self._request_od()
        self._auth_as('hodcs')
        self.client.post(reverse('od-request-reject', args=[od_request.id]), {'reason': 'Not eligible'})
        self._auth_as('odstudent')
        response = self.client.get(reverse('od-request-detail', args=[od_request.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], ODRequest.Status.REJECTED)
        self.assertEqual(response.data['rejection_reason'], 'Not eligible')
        self.assertEqual(response.data['reason'], 'Inter-college fest')

    def test_admin_can_approve_system_wide(self):
        od_request = self._request_od()
        self._auth_as('sysadmin')
        response = self.client.post(reverse('od-request-approve', args=[od_request.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
