"""Manual attendance marking (requirements 11 and 15).

Attendance is the Event Coordinator's responsibility. Faculty verify evidence
and may request attendance, but they never set the attendance record itself,
and nothing in the system turns a registration or a live capture into
attendance on its own.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.audit.models import AuditLog
from apps.registrations.models import Registration

from .helpers import (
    make_college,
    make_department,
    make_event,
    make_event_coordinator,
    make_faculty,
    make_student,
)


class ManualAttendanceTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.college = make_college()
        self.coordinator = make_event_coordinator('ec1', self.department)
        self.faculty = make_faculty('fac1', self.department)
        self.student = make_student('stu1', self.department)
        self.event = make_event(
            created_by=self.coordinator, college=self.college, department=self.department,
        )
        # Registered, but never captured: exactly the student requirement 15 is
        # about. There is no Participation row at all here.
        self.registration = Registration.objects.create(student=self.student, event=self.event)
        self.url = reverse('attendance-mark')

    def _mark(self, **payload):
        body = {'registration': self.registration.id, 'status': 'APPROVED'}
        body.update(payload)
        return self.client.post(self.url, body, format='json')

    def test_coordinator_can_mark_a_student_who_never_captured(self):
        self.client.force_authenticate(self.coordinator)
        response = self._mark()

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        attendance = Attendance.objects.get(registration=self.registration)
        self.assertEqual(attendance.status, Attendance.Status.APPROVED)
        self.assertIsNone(attendance.participation_id)
        self.assertTrue(attendance.is_manual)
        self.assertEqual(attendance.reviewed_by_id, self.coordinator.id)

    def test_marking_again_updates_the_same_record(self):
        self.client.force_authenticate(self.coordinator)
        self._mark()
        response = self._mark(status='REJECTED', reason='Did not attend')

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(Attendance.objects.filter(registration=self.registration).count(), 1)
        attendance = Attendance.objects.get(registration=self.registration)
        self.assertEqual(attendance.status, Attendance.Status.REJECTED)
        self.assertEqual(attendance.rejection_reason, 'Did not attend')

    def test_rejecting_requires_a_reason(self):
        self.client.force_authenticate(self.coordinator)
        response = self._mark(status='REJECTED', reason='   ')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Attendance.objects.filter(registration=self.registration).exists())

    def test_faculty_cannot_mark_attendance(self):
        self.client.force_authenticate(self.faculty)
        response = self._mark()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Attendance.objects.exists())

    def test_a_student_cannot_mark_their_own_attendance(self):
        self.client.force_authenticate(self.student)
        response = self._mark()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Attendance.objects.exists())

    def test_a_coordinator_from_another_department_cannot_mark(self):
        other_department = make_department('EC', 'Electronics')
        outsider = make_event_coordinator('ec2', other_department)
        self.client.force_authenticate(outsider)

        response = self._mark()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Attendance.objects.exists())

    def test_marking_is_recorded_in_the_audit_trail(self):
        self.client.force_authenticate(self.coordinator)
        self._mark()

        self.assertTrue(
            AuditLog.objects.filter(
                action='ATTENDANCE_MARKED_MANUALLY', actor=self.coordinator,
            ).exists(),
        )

    def test_registration_alone_never_creates_attendance(self):
        # The registration exists and the event has happened; nothing should
        # have recorded attendance until a coordinator says so.
        self.assertFalse(Attendance.objects.filter(registration=self.registration).exists())

    def test_only_approved_or_rejected_can_be_set(self):
        self.client.force_authenticate(self.coordinator)
        response = self._mark(status='PENDING')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
