"""
Phase 9 §7 — protected fields submitted by a client are ignored or refused
on every writable endpoint. Each test submits the *legitimate* payload plus
every server-owned field it can think of, then checks the stored row.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.events.models import Event
from apps.notifications.models import Notification
from apps.od.models import ODRequest
from apps.participation.models import Participation
from apps.registrations.models import Registration

from .helpers import AuthMixin, build_universe, make_department, make_registration

FAKE_TS = '2001-01-01T00:00:00Z'


class MassAssignmentTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()

    def test_event_create_ignores_status_owner_and_department(self):
        self._auth_as('hodb')
        today = timezone.localdate()
        response = self.client.post(reverse('event-list'), {
            'title': 'Injected Event', 'venue': 'Hall', 'category': 'Technical',
            'event_date': str(today + timedelta(days=10)), 'conducting_college': self.u.college.id,
            'registration_start_date': str(today), 'registration_end_date': str(today + timedelta(days=5)),
            # protected:
            'status': 'PUBLISHED', 'created_by': self.u.admin.id, 'department': self.u.a.department.id,
            'id': 999999, 'created_at': FAKE_TS, 'updated_at': FAKE_TS,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        event = Event.objects.get(title='Injected Event')
        self.assertEqual(event.status, Event.Status.DRAFT)
        self.assertEqual(event.created_by_id, self.u.b.event_coordinator.id)
        self.assertEqual(event.department_id, self.u.b.department.id)
        self.assertNotEqual(event.id, 999999)
        self.assertGreater(event.created_at.year, 2001)

    def test_event_update_cannot_change_status_owner_or_department(self):
        self._auth_as('hoda')
        event = self.u.a.draft_event
        response = self.client.patch(reverse('event-detail', args=[event.id]), {
            'title': 'Renamed', 'status': 'PUBLISHED', 'created_by': self.u.admin.id,
            'department': self.u.b.department.id,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        event.refresh_from_db()
        self.assertEqual(event.title, 'Renamed')
        self.assertEqual(event.status, Event.Status.DRAFT)
        self.assertEqual(event.created_by_id, self.u.a.event_coordinator.id)
        self.assertEqual(event.department_id, self.u.a.department.id)

    def test_registration_create_ignores_student_status_and_timestamps(self):
        self._auth_as('studenta2')
        response = self.client.post(reverse('registration-list'), {
            'event': self.u.a.open_event.id, 'student': self.u.a.student.id, 'status': 'CANCELLED',
            'registered_at': FAKE_TS, 'cancelled_at': FAKE_TS,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        registration = Registration.objects.get(event=self.u.a.open_event, student=self.u.a.other_student)
        self.assertEqual(registration.status, Registration.Status.REGISTERED)
        self.assertIsNone(registration.cancelled_at)
        self.assertFalse(Registration.objects.filter(event=self.u.a.open_event, student=self.u.a.student).exists())

    def test_participation_open_ignores_student_registration_and_status(self):
        make_registration(student=self.u.a.other_student, event=self.u.a.event)
        self._auth_as('studenta2')
        response = self.client.post(reverse('participation-list'), {
            'event': self.u.a.event.id, 'student': self.u.a.student.id,
            'registration': self.u.a.registration.id, 'status': 'SUBMITTED', 'submitted_at': FAKE_TS,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        participation = Participation.objects.get(pk=response.data['id'])
        self.assertEqual(participation.student_id, self.u.a.other_student.id)
        self.assertEqual(participation.status, Participation.Status.DRAFT)
        self.assertIsNone(participation.submitted_at)

    def test_attendance_request_ignores_status_reviewer_and_timestamps(self):
        self.u.a.attendance.delete()
        self._auth_as('facultya')
        response = self.client.post(reverse('attendance-list'), {
            'participation': self.u.a.participation.id, 'status': 'APPROVED', 'reviewed_by': self.u.a.faculty.id,
            'reviewed_at': FAKE_TS, 'requested_by': self.u.admin.id, 'rejection_reason': 'x',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        attendance = Attendance.objects.get(participation=self.u.a.participation)
        self.assertEqual(attendance.status, Attendance.Status.PENDING)
        self.assertIsNone(attendance.reviewed_by)
        self.assertIsNone(attendance.reviewed_at)
        self.assertEqual(attendance.requested_by_id, self.u.a.faculty.id)

    def test_od_request_ignores_status_and_reviewer(self):
        self.u.a.od.delete()
        self._auth_as('facultya')
        response = self.client.post(reverse('od-request-list'), {
            'participation': self.u.a.participation.id, 'reason': 'fest', 'status': 'APPROVED',
            'reviewed_by': self.u.a.faculty.id, 'reviewed_at': FAKE_TS,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        od = ODRequest.objects.get(participation=self.u.a.participation)
        self.assertEqual(od.status, ODRequest.Status.PENDING)
        self.assertIsNone(od.reviewed_by)

    def test_achievement_create_by_faculty_cannot_self_approve(self):
        self._auth_as('facultya')
        response = self.client.post(reverse('achievement-list'), {
            'participation': self.u.a.participation.id, 'title': 'Self-approved', 'achievement_type': 'Competition',
            'achievement_date': str(self.u.a.event.event_date),
            'status': 'APPROVED', 'reviewed_by': self.u.a.event_coordinator.id, 'reviewed_at': FAKE_TS,
            'created_by': self.u.a.event_coordinator.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        achievement = Achievement.objects.get(title='Self-approved')
        self.assertEqual(achievement.status, Achievement.Status.PENDING_APPROVAL)
        self.assertIsNone(achievement.reviewed_by)
        self.assertEqual(achievement.created_by_id, self.u.a.faculty.id)

    def test_achievement_patch_cannot_change_status_or_participation(self):
        achievement = Achievement.objects.create(
            participation=self.u.a.participation, created_by=self.u.a.faculty, title='Draft',
            achievement_type='Competition', achievement_date=self.u.a.event.event_date,
            status=Achievement.Status.DRAFT,
        )
        self._auth_as('facultya')
        response = self.client.patch(reverse('achievement-detail', args=[achievement.id]), {
            'title': 'Edited', 'status': 'APPROVED', 'participation': self.u.b.participation.id,
            'created_by': self.u.a.event_coordinator.id, 'reviewed_by': self.u.a.event_coordinator.id,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        achievement.refresh_from_db()
        self.assertEqual(achievement.title, 'Edited')
        self.assertEqual(achievement.status, Achievement.Status.DRAFT)
        self.assertEqual(achievement.participation_id, self.u.a.participation.id)
        self.assertEqual(achievement.created_by_id, self.u.a.faculty.id)

    def test_decision_endpoints_ignore_client_status_reviewer_and_decision_fields(self):
        self._auth_as('hoda')
        response = self.client.post(reverse('attendance-approve', args=[self.u.a.attendance.id]), {
            'status': 'REJECTED', 'reviewed_by': self.u.admin.id, 'reviewed_at': FAKE_TS,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        attendance = Attendance.objects.get(pk=self.u.a.attendance.pk)
        self.assertEqual(attendance.status, Attendance.Status.APPROVED)
        self.assertEqual(attendance.reviewed_by_id, self.u.a.event_coordinator.id)
        self.assertGreater(attendance.reviewed_at.year, 2001)

    def test_faculty_verify_cannot_smuggle_a_different_decision_or_reviewer(self):
        from apps.verification.models import Evidence, EvidenceVerification
        self.u.b.verification.delete()
        Evidence.objects.filter(pk=self.u.b.evidence.pk).update(status=Evidence.Status.SUBMITTED)
        self._auth_as('facultyb')
        response = self.client.post(reverse('evidence-verify', args=[self.u.b.evidence.id]), {
            'decision': 'REJECTED', 'reviewer': self.u.admin.id, 'is_event_coordinator_override': True, 'reason': '',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        verification = EvidenceVerification.objects.get(evidence_version=self.u.b.version)
        self.assertEqual(verification.decision, EvidenceVerification.Decision.VERIFIED)
        self.assertEqual(verification.reviewer_id, self.u.b.faculty.id)
        self.assertFalse(verification.is_event_coordinator_override)

    def test_notification_read_ignores_client_read_at_and_recipient(self):
        self._auth_as('studenta')
        response = self.client.post(reverse('notification-read', args=[self.u.a.notification.id]), {
            'read_at': FAKE_TS, 'recipient': self.u.b.student.id, 'is_read': False,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification = Notification.objects.get(pk=self.u.a.notification.pk)
        self.assertTrue(notification.is_read)
        self.assertGreater(notification.read_at.year, 2001)
        self.assertEqual(notification.recipient_id, self.u.a.student.id)

    def test_public_registration_cannot_self_activate_or_escalate(self):
        from apps.accounts.models import User
        response = self.client.post(reverse('auth-register'), {
            'username': 'escalate', 'email': 'escalate@example.com', 'full_name': 'Esca Late',
            'password': 'Another$trong9', 'confirm_password': 'Another$trong9',
            'role': 'STUDENT', 'department': self.u.a.department.id,
            'university_registration_number': '1AY22MC777',
            'is_active': True, 'is_superuser': True, 'is_staff': True,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(username='escalate')
        self.assertFalse(user.is_active)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

        # Admin is the only role that can never be self-registered. Event
        # Coordinator now can be — but registering as one must still not hand
        # out staff or superuser rights, which is what this test is about.
        response = self.client.post(reverse('auth-register'), {
            'username': 'adminx', 'email': 'ADMIN@example.com', 'full_name': 'Ad Min',
            'password': 'Another$trong9', 'confirm_password': 'Another$trong9',
            'role': 'ADMIN', 'department': self.u.a.department.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        coordinator_department = make_department('ZZ', 'Coordinatorless Department')
        response = self.client.post(reverse('auth-register'), {
            'username': 'coordx', 'email': 'coordx@example.com', 'full_name': 'Co Ord',
            'password': 'Another$trong9', 'confirm_password': 'Another$trong9',
            'role': 'EVENT_COORDINATOR', 'department': coordinator_department.id,
            # Required since an Event Coordinator is recognised as a faculty
            # member; supplied so the request reaches the escalation
            # assertions below, which are what this test is really about.
            'faculty_id': 'FAC-ESCALATE-1',
            'is_superuser': True, 'is_staff': True,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        coordinator = User.objects.get(username='coordx')
        self.assertTrue(coordinator.is_active)  # active by design, not by escalation
        self.assertFalse(coordinator.is_superuser)
        self.assertFalse(coordinator.is_staff)
