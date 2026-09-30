"""
Service-layer behaviour: deduplication, the "notification failure must not
break the business action" guarantee, and route sanitisation.
"""

from unittest import mock

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.notifications import services
from apps.notifications.models import Notification

from .helpers import (
    AuthMixin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)


class NotificationDeduplicationTests(TestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.student = make_student('dedupestudent', self.cs)

    def test_same_dedupe_key_creates_only_one_notification(self):
        for _ in range(5):
            services.create_notification(
                recipient=self.student,
                notification_type=Notification.Type.ATTENDANCE_APPROVED,
                title='Attendance approved', message='Once only.',
                dedupe_key='attendance:1:decision:student',
            )
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 1)

    def test_different_dedupe_keys_create_separate_notifications(self):
        services.create_notification(
            recipient=self.student, notification_type=Notification.Type.ATTENDANCE_APPROVED,
            title='A', message='A', dedupe_key='attendance:1:decision:student',
        )
        services.create_notification(
            recipient=self.student, notification_type=Notification.Type.OD_APPROVED,
            title='B', message='B', dedupe_key='od:1:decision:student',
        )
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 2)

    def test_blank_dedupe_key_does_not_deduplicate(self):
        """Notifications that may legitimately recur opt out by leaving the
        key blank; the partial unique index ignores them."""
        for _ in range(3):
            services.create_notification(
                recipient=self.student, notification_type=Notification.Type.EVENT_PUBLISHED,
                title='Event', message='Recurring', dedupe_key='',
            )
        self.assertEqual(Notification.objects.filter(recipient=self.student).count(), 3)

    def test_no_recipient_is_not_an_error(self):
        """A department with no active Event Coordinator yet is a normal state, not a
        failure — the helper returns None and nothing is created."""
        result = services.create_notification(
            recipient=None, notification_type=Notification.Type.ATTENDANCE_REQUESTED,
            title='x', message='y',
        )
        self.assertIsNone(result)
        self.assertEqual(Notification.objects.count(), 0)


class NotificationRouteSafetyTests(TestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.student = make_student('routestudent', self.cs)

    def test_external_and_protocol_relative_routes_are_dropped(self):
        for hostile in (
            'https://evil.example.com',
            '//evil.example.com',
            'javascript:alert(1)',
            '/\\evil.example.com',
            'http://evil.example.com/path',
        ):
            notification = services.create_notification(
                recipient=self.student, notification_type=Notification.Type.EVENT_PUBLISHED,
                title='t', message='m', action_route=hostile,
            )
            self.assertEqual(notification.action_route, '', f'{hostile!r} should have been dropped')

    def test_internal_routes_are_preserved(self):
        notification = services.create_notification(
            recipient=self.student, notification_type=Notification.Type.EVENT_PUBLISHED,
            title='t', message='m', action_route='/student/attendance',
        )
        self.assertEqual(notification.action_route, '/student/attendance')


class NotificationFailureIsolationTests(AuthMixin, APITestCase):
    """The core guarantee: an academic decision must survive a broken
    notification pipeline."""

    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('isolationstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )

    def test_attendance_approval_survives_a_failing_notification(self):
        attendance = Attendance.objects.create(
            participation=self.participation, requested_by=self.faculty,
        )
        self._auth_as('hodcs')
        with mock.patch.object(
            services, 'create_notification', side_effect=RuntimeError('notification backend down'),
        ):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse('attendance-approve', args=[attendance.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(Attendance.objects.get(pk=attendance.id).status, Attendance.Status.APPROVED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_service_helper_swallows_and_logs_rather_than_raising(self):
        with mock.patch.object(
            services, 'create_notification', side_effect=RuntimeError('boom'),
        ):
            # _safe must absorb this; if it propagated, the on_commit callback
            # would surface the error to the caller.
            result = services.notify_attendance_request(
                attendance=Attendance.objects.create(
                    participation=self.participation, requested_by=self.faculty,
                ),
            )
        self.assertIsNone(result)
