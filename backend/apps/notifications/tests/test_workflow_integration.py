"""
Notifications produced by real business actions across Phases 1-5.

These go through the actual API rather than calling the notification service
directly, so they prove the wiring — including that `transaction.on_commit`
callbacks actually fire. `APITestCase` wraps each test in a transaction that
is rolled back, which would normally mean on_commit callbacks never run; the
`captureOnCommitCallbacks` context manager runs them at the right moment,
which is exactly what Django provides it for.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.notifications.models import Notification
from apps.od.models import ODRequest
from apps.registrations.models import Registration
from apps.verification.models import EvidenceVerification

from .helpers import (
    AuthMixin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_submitted_evidence,
    make_participation,
    make_todays_published_event,
    make_verified_participation,
)


class NotificationWorkflowTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('notifstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )

    def _notifications_for(self, user, notification_type=None):
        queryset = Notification.objects.filter(recipient=user)
        if notification_type:
            queryset = queryset.filter(notification_type=notification_type)
        return queryset

    # --- evidence (Phase 4) -------------------------------------------------

    def test_evidence_verification_notifies_the_student(self):
        participation = make_participation(student=self.student, event=self.event)
        evidence, _version = make_submitted_evidence(participation=participation)

        self._auth_as('facultycs')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('evidence-verify', args=[evidence.id]), {'reason': 'looks good'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        notification = self._notifications_for(
            self.student, Notification.Type.EVIDENCE_VERIFIED,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn(self.event.title, notification.title)
        self.assertEqual(notification.action_route, '/student/participation')

    def test_resubmission_request_notifies_student_with_the_faculty_reason(self):
        participation = make_participation(student=self.student, event=self.event)
        evidence, _version = make_submitted_evidence(participation=participation)

        self._auth_as('facultycs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('evidence-request-resubmission', args=[evidence.id]),
                {'reason': 'Face not clearly visible'},
            )

        notification = self._notifications_for(
            self.student, Notification.Type.EVIDENCE_RESUBMISSION_REQUIRED,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('Face not clearly visible', notification.message)
        self.assertEqual(notification.action_route, f'/student/participation/{participation.id}/resubmit')

    def test_evidence_notification_leaks_no_capture_metadata(self):
        """Only the decision and the reviewer's stated reason are sent — never
        coordinates, hashes or device timestamps."""
        participation = make_participation(student=self.student, event=self.event)
        evidence, version = make_submitted_evidence(participation=participation)
        capture = version.captures.first()

        self._auth_as('facultycs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('evidence-verify', args=[evidence.id]))

        notification = self._notifications_for(self.student).first()
        body = f'{notification.title} {notification.message}'
        self.assertNotIn(capture.sha256_hash, body)
        self.assertNotIn(str(capture.latitude), body)
        self.assertNotIn(str(capture.longitude), body)

    def test_event_coordinator_override_notifies_the_student(self):
        participation = make_participation(student=self.student, event=self.event)
        evidence, version = make_submitted_evidence(participation=participation)
        EvidenceVerification.objects.create(
            evidence_version=version, reviewer=self.faculty,
            decision=EvidenceVerification.Decision.VERIFIED, reason='ok',
        )

        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse('evidence-override', args=[evidence.id]),
                {'decision': 'REJECTED', 'reason': 'Reviewed personally'},
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertTrue(self._notifications_for(self.student, Notification.Type.EVENT_COORDINATOR_OVERRIDE).exists())

    # --- attendance / OD (Phase 5) -----------------------------------------

    def test_attendance_request_notifies_the_event_coordinator(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self._auth_as('facultycs')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('attendance-list'), {'participation': participation.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        notification = self._notifications_for(self.event_coordinator, Notification.Type.ATTENDANCE_REQUESTED).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.action_route, '/event_coordinator/attendance')
        # The student is not told about a request that has not been decided.
        self.assertFalse(self._notifications_for(self.student).exists())

    def test_attendance_approval_notifies_both_student_and_requesting_faculty(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        attendance = Attendance.objects.create(participation=participation, requested_by=self.faculty)

        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('attendance-approve', args=[attendance.id]))

        self.assertTrue(
            self._notifications_for(self.student, Notification.Type.ATTENDANCE_APPROVED).exists(),
        )
        self.assertTrue(
            self._notifications_for(self.faculty, Notification.Type.ATTENDANCE_APPROVED).exists(),
        )

    def test_attendance_rejection_includes_the_reason_for_the_student(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        attendance = Attendance.objects.create(participation=participation, requested_by=self.faculty)

        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(
                reverse('attendance-reject', args=[attendance.id]), {'reason': 'Insufficient evidence'},
            )

        notification = self._notifications_for(
            self.student, Notification.Type.ATTENDANCE_REJECTED,
        ).first()
        self.assertIsNotNone(notification)
        self.assertIn('Insufficient evidence', notification.message)

    def test_od_request_and_decision_notify_the_right_people(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self._auth_as('facultycs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('od-request-list'), {'participation': participation.id, 'reason': 'Fest'})
        self.assertTrue(self._notifications_for(self.event_coordinator, Notification.Type.OD_REQUESTED).exists())

        od_request = ODRequest.objects.get(participation=participation)
        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('od-request-approve', args=[od_request.id]))

        self.assertTrue(self._notifications_for(self.student, Notification.Type.OD_APPROVED).exists())
        self.assertTrue(self._notifications_for(self.faculty, Notification.Type.OD_APPROVED).exists())

    # --- achievements (Phase 5) --------------------------------------------

    def test_faculty_achievement_notifies_event_coordinator_but_event_coordinator_created_one_does_not(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        payload = {
            'participation': participation.id, 'title': 'First Place',
            'achievement_type': 'Competition', 'achievement_date': str(self.event.event_date),
        }
        self._auth_as('facultycs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('achievement-list'), payload)
        self.assertEqual(
            self._notifications_for(self.event_coordinator, Notification.Type.ACHIEVEMENT_CREATED).count(), 1,
        )

        # An Event Coordinator-created achievement is authoritative immediately, so there is
        # nobody to ask for approval and no notification to send.
        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('achievement-list'), {**payload, 'title': 'Second Place'})
        self.assertEqual(
            self._notifications_for(self.event_coordinator, Notification.Type.ACHIEVEMENT_CREATED).count(), 1,
        )

    def test_achievement_approval_notifies_student_and_creator(self):
        participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self._auth_as('facultycs')
        created = self.client.post(reverse('achievement-list'), {
            'participation': participation.id, 'title': 'First Place',
            'achievement_type': 'Competition', 'achievement_date': str(self.event.event_date),
        })
        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('achievement-approve', args=[created.data['id']]))

        self.assertTrue(
            self._notifications_for(self.student, Notification.Type.ACHIEVEMENT_APPROVED).exists(),
        )
        self.assertTrue(
            self._notifications_for(self.faculty, Notification.Type.ACHIEVEMENT_APPROVED).exists(),
        )

    # --- events (Phase 2) ---------------------------------------------------

    def test_event_cancellation_notifies_only_registered_students(self):
        registered = make_student('registeredstudent', self.cs)
        unregistered = make_student('unregisteredstudent', self.cs)
        Registration.objects.create(student=registered, event=self.event)

        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('event-cancel', args=[self.event.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertTrue(
            self._notifications_for(registered, Notification.Type.EVENT_CANCELLED).exists(),
        )
        self.assertFalse(
            self._notifications_for(unregistered, Notification.Type.EVENT_CANCELLED).exists(),
        )

    def test_event_publication_notifies_department_students_only(self):
        other_dept = make_department('EC', 'Electronics')
        in_dept = make_student('indeptstudent', self.cs)
        out_of_dept = make_student('outdeptstudent', other_dept)

        draft = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
            title='Draft Event', status='DRAFT',
        )
        self._auth_as('hodcs')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('event-publish', args=[draft.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        self.assertTrue(self._notifications_for(in_dept, Notification.Type.EVENT_PUBLISHED).exists())
        self.assertFalse(self._notifications_for(out_of_dept, Notification.Type.EVENT_PUBLISHED).exists())
