"""
Shared fixtures for the cross-app Phase 9 hardening tests.

`build_universe()` creates two departments with a full cast in each, one
record of every resource type per student, and returns them as attributes so
the authorization / IDOR matrices can name "Student A's evidence" or
"department B's attendance" directly. Everything is created through the
existing per-app helpers so the fixture can never drift from what the apps
consider a valid record.
"""

from django.urls import reverse
from rest_framework import status

from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.notifications import services as notifications
from apps.notifications.models import Notification
from apps.od.models import ODRequest
from apps.verification.models import Evidence, EvidenceVerification
from apps.verification.tests.helpers import (
    make_admin,
    make_college,
    make_department,
    make_event,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_registration,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
    make_verified_participation,
)

DEFAULT_PASSWORD = 'StrongPass123!'

__all__ = [
    'DEFAULT_PASSWORD', 'AuthMixin', 'build_universe', 'make_admin', 'make_college', 'make_department',
    'make_event', 'make_faculty', 'make_event_coordinator', 'make_participation', 'make_registration', 'make_student',
    'make_submitted_evidence', 'make_todays_published_event', 'make_verified_participation',
]


class AuthMixin:
    def _auth_as(self, username, password=DEFAULT_PASSWORD):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': password})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        return login.data

    def _anon(self):
        self.client.credentials()


class Universe:
    pass


def _side(u, *, code, name, suffix, event_coordinator_username, faculty_username, student_username):
    """One department with its Event Coordinator, Faculty, one student and one record of
    every resource type for that student."""
    side = Universe()
    side.department = make_department(code, name)
    side.event_coordinator = make_event_coordinator(event_coordinator_username, side.department)
    side.faculty = make_faculty(faculty_username, side.department)
    side.student = make_student(student_username, side.department)
    side.event = make_todays_published_event(
        created_by=side.event_coordinator, college=u.college, department=side.department, title=f'Event {suffix}',
    )
    side.open_event = make_event(
        created_by=side.event_coordinator, college=u.college, department=side.department, title=f'Open {suffix}',
        status='PUBLISHED', days_until_event=10, registration_starts_in=-1, registration_ends_in=5,
    )
    side.draft_event = make_event(
        created_by=side.event_coordinator, college=u.college, department=side.department, title=f'Draft {suffix}',
        status='DRAFT', days_until_event=10, registration_starts_in=-1, registration_ends_in=5,
    )
    side.participation = make_verified_participation(student=side.student, event=side.event, reviewer=side.faculty)
    side.registration = side.participation.registration
    side.evidence = Evidence.objects.get(participation=side.participation)
    side.version = side.evidence.current_version
    side.capture = side.version.captures.first()
    side.verification = EvidenceVerification.objects.get(evidence_version=side.version)
    side.attendance = Attendance.objects.create(participation=side.participation, requested_by=side.faculty)
    side.od = ODRequest.objects.create(participation=side.participation, requested_by=side.faculty, reason='fest')
    side.achievement = Achievement.objects.create(
        participation=side.participation, created_by=side.faculty, title=f'Prize {suffix}',
        achievement_type='Competition', achievement_date=side.event.event_date,
        status=Achievement.Status.PENDING_APPROVAL,
    )
    side.notification = notifications.create_notification(
        recipient=side.student, notification_type=Notification.Type.EVIDENCE_VERIFIED,
        title=f'Verified {suffix}', message='Your evidence was verified.', action_route='/student/participation',
    )
    return side


def build_universe():
    u = Universe()
    u.college = make_college()
    u.admin = make_admin('sysadmin')
    u.a = _side(u, code='CS', name='Computer Science', suffix='A',
                event_coordinator_username='hoda', faculty_username='facultya', student_username='studenta')
    u.b = _side(u, code='EC', name='Electronics', suffix='B',
                event_coordinator_username='hodb', faculty_username='facultyb', student_username='studentb')
    # A second student in department A with nothing of their own, for
    # "same department, different student" attempts.
    u.a.other_student = make_student('studenta2', u.a.department)
    return u
