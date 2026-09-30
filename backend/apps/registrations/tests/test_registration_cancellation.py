from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event
from apps.registrations.models import Registration

from .helpers import (
    make_admin, make_college, make_department, make_event, make_event_coordinator, make_registration, make_student,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class RegistrationCancellationTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.admin = make_admin('siteadmin')
        self.student = make_student('studentcs', self.department)
        self.other_student = make_student('otherstudent', self.department)

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_student_can_cancel_own_registration(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        registration = make_registration(student=self.student, event=event)
        self._auth_as('studentcs')
        response = self.client.post(reverse('registration-cancel', args=[registration.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.CANCELLED)
        self.assertIsNotNone(registration.cancelled_at)

    def test_student_cannot_cancel_another_students_registration(self):
        # Another student's registration is outside this student's visible
        # queryset entirely, so the API correctly returns 404 rather than
        # 403 — it never confirms the registration's existence to a student
        # who isn't authorized to see it (see test_registration_access).
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        registration = make_registration(student=self.other_student, event=event)
        self._auth_as('studentcs')
        response = self.client.post(reverse('registration-cancel', args=[registration.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.REGISTERED)

    def test_cannot_cancel_already_cancelled_registration(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        registration = make_registration(student=self.student, event=event, status=Registration.Status.CANCELLED)
        self._auth_as('studentcs')
        response = self.client.post(reverse('registration-cancel', args=[registration.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_registration_for_past_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.COMPLETED,
            days_until_event=-3, registration_starts_in=-10, registration_ends_in=-5,
        )
        registration = make_registration(student=self.student, event=event)
        self._auth_as('studentcs')
        response = self.client.post(reverse('registration-cancel', args=[registration.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.REGISTERED)

    def test_registration_survives_event_cancellation_unchanged(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        registration = make_registration(student=self.student, event=event)

        self._auth_as('hodcs')
        cancel_response = self.client.post(reverse('event-cancel', args=[event.id]))
        self.assertEqual(cancel_response.status_code, status.HTTP_200_OK)

        registration.refresh_from_db()
        self.assertEqual(registration.status, Registration.Status.REGISTERED)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELLED)

    def test_admin_can_cancel_any_students_registration(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        registration = make_registration(student=self.student, event=event)
        self._auth_as('siteadmin')
        response = self.client.post(reverse('registration-cancel', args=[registration.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_event_coordinator_cannot_cancel_a_students_registration(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        registration = make_registration(student=self.student, event=event)
        self._auth_as('hodcs')
        response = self.client.post(reverse('registration-cancel', args=[registration.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
