"""Faculty requests -> Event Coordinator approves/rejects. Faculty never approve."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.audit.models import AuditLog
from apps.verification.models import EvidenceVerification

from .helpers import (
    AuthMixin,
    make_admin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)

Decision = EvidenceVerification.Decision


class AttendanceWorkflowTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.admin = make_admin('sysadmin')
        self.student = make_student('wfstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self.list_url = reverse('attendance-list')

    def _request_attendance(self):
        self._auth_as('facultycs')
        response = self.client.post(self.list_url, {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        return Attendance.objects.get(pk=response.data['id'])

    # --- requesting ---------------------------------------------------------

    def test_faculty_can_request_attendance_and_it_is_audit_logged(self):
        attendance = self._request_attendance()
        self.assertEqual(attendance.status, Attendance.Status.PENDING)
        self.assertEqual(attendance.requested_by_id, self.faculty.id)
        self.assertIsNone(attendance.reviewed_by_id)
        self.assertIsNone(attendance.reviewed_at)
        self.assertTrue(AuditLog.objects.filter(action='ATTENDANCE_REQUESTED', actor=self.faculty).exists())

    def test_student_cannot_request_attendance(self):
        self._auth_as('wfstudent')
        response = self.client.post(self.list_url, {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_coordinator_cannot_request_attendance(self):
        self._auth_as('hodcs')
        response = self.client.post(self.list_url, {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_impersonate_the_faculty_request_role(self):
        self._auth_as('sysadmin')
        response = self.client.post(self.list_url, {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- approving ----------------------------------------------------------

    def test_event_coordinator_can_approve_and_the_record_becomes_official(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Attendance.Status.APPROVED)
        self.assertEqual(response.data['reviewed_by']['username'], 'hodcs')
        self.assertIsNotNone(response.data['reviewed_at'])
        self.assertTrue(AuditLog.objects.filter(action='ATTENDANCE_APPROVED', actor=self.event_coordinator).exists())

    def test_admin_can_approve_system_wide(self):
        attendance = self._request_attendance()
        self._auth_as('sysadmin')
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Attendance.Status.APPROVED)

    def test_faculty_cannot_approve_attendance(self):
        attendance = self._request_attendance()
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Attendance.objects.get(pk=attendance.id).status, Attendance.Status.PENDING)

    def test_student_cannot_approve_their_own_attendance(self):
        attendance = self._request_attendance()
        self._auth_as('wfstudent')
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approval_is_refused_if_an_event_coordinator_override_removed_verification_first(self):
        """The eligibility check is re-run at decision time, not only at
        request time — an override that lands between the two must block it."""
        attendance = self._request_attendance()
        version = self.participation.evidence.current_version
        EvidenceVerification.objects.create(
            evidence_version=version, reviewer=self.event_coordinator, decision=Decision.REJECTED,
            reason='reviewed personally', is_event_coordinator_override=True,
        )
        self._auth_as('hodcs')
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attendance.objects.get(pk=attendance.id).status, Attendance.Status.PENDING)

    # --- rejecting ----------------------------------------------------------

    def test_event_coordinator_reject_requires_a_reason(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        response = self.client.post(reverse('attendance-reject', args=[attendance.id]), {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attendance.objects.get(pk=attendance.id).status, Attendance.Status.PENDING)

    def test_event_coordinator_reject_with_blank_reason_is_refused(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        response = self.client.post(reverse('attendance-reject', args=[attendance.id]), {'reason': '   '})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_event_coordinator_can_reject_with_a_reason_and_the_record_is_preserved(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        response = self.client.post(
            reverse('attendance-reject', args=[attendance.id]), {'reason': 'Evidence insufficient'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['status'], Attendance.Status.REJECTED)
        self.assertEqual(response.data['rejection_reason'], 'Evidence insufficient')
        # Not deleted — the rejected record stays visible to student and faculty.
        self.assertTrue(Attendance.objects.filter(pk=attendance.id).exists())
        self.assertTrue(AuditLog.objects.filter(action='ATTENDANCE_REJECTED').exists())

    # --- finality -----------------------------------------------------------

    def test_an_approved_request_cannot_be_approved_again(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        self.client.post(reverse('attendance-approve', args=[attendance.id]))
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_rejected_request_cannot_later_be_approved(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        self.client.post(reverse('attendance-reject', args=[attendance.id]), {'reason': 'no'})
        response = self.client.post(reverse('attendance-approve', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Attendance.objects.get(pk=attendance.id).status, Attendance.Status.REJECTED)

    # --- reading ------------------------------------------------------------

    def test_student_can_read_their_own_attendance_status(self):
        attendance = self._request_attendance()
        self._auth_as('hodcs')
        self.client.post(reverse('attendance-reject', args=[attendance.id]), {'reason': 'Evidence insufficient'})
        self._auth_as('wfstudent')
        response = self.client.get(reverse('attendance-detail', args=[attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Attendance.Status.REJECTED)
        self.assertEqual(response.data['rejection_reason'], 'Evidence insufficient')
        self.assertEqual(response.data['event']['title'], self.event.title)
