from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event
from apps.registrations.models import Registration

from .helpers import (
    make_admin, make_college, make_department, make_event, make_faculty, make_event_coordinator, make_student,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class RegistrationCreationTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.admin = make_admin('siteadmin')
        self.faculty = make_faculty('facultycs', self.department)
        self.student = make_student('studentcs', self.department)
        self.url = reverse('registration-list')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_student_can_register_for_open_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        registration = Registration.objects.get(student=self.student, event=event)
        self.assertEqual(registration.status, Registration.Status.REGISTERED)

    def test_duplicate_registration_is_rejected(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('studentcs')
        self.client.post(self.url, {'event': event.id})
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Registration.objects.filter(student=self.student, event=event).count(), 1)

    def test_database_uniqueness_is_enforced_even_bypassing_serializer_precheck(self):
        from django.db import IntegrityError
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        Registration.objects.create(student=self.student, event=event)
        with self.assertRaises(IntegrityError):
            Registration.objects.create(student=self.student, event=event)

    def test_registration_to_draft_event_is_rejected(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_to_cancelled_event_is_rejected(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.CANCELLED,
        )
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_to_completed_event_is_rejected(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.COMPLETED,
        )
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_before_window_starts_is_rejected(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
            registration_starts_in=2, registration_ends_in=5,
        )
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_registration_after_window_ends_is_rejected(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
            days_until_event=10, registration_starts_in=-5, registration_ends_in=-1,
        )
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_cannot_register(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('facultycs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_coordinator_cannot_register(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('hodcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_register(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('siteadmin')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_register(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_register_another_student_by_manipulating_payload(self):
        other_student = make_student('otherstudent', self.department)
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('studentcs')
        response = self.client.post(self.url, {'event': event.id, 'student': other_student.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        registration = Registration.objects.get(event=event)
        self.assertEqual(registration.student_id, self.student.id)
        self.assertNotEqual(registration.student_id, other_student.id)
