from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event
from apps.participation.models import Participation
from apps.registrations.models import Registration

from .helpers import (
    make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_registration, make_student,
    make_todays_published_event,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class ParticipationCreationTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.admin = make_admin('siteadmin')
        self.faculty = make_faculty('facultycs', self.department)
        self.student = make_student('createstudent', self.department)
        self.url = reverse('participation-list')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_eligible_student_can_open_participation(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('createstudent')

        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['status'], 'DRAFT')

        participation = Participation.objects.get(id=response.data['id'])
        self.assertEqual(participation.student_id, self.student.id)
        self.assertEqual(participation.event_id, event.id)

    def test_unregistered_student_is_rejected(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self._auth_as('createstudent')

        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(Participation.objects.filter(student=self.student).exists())

    def test_cancelled_registration_is_rejected(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        registration = make_registration(student=self.student, event=event)
        registration.status = Registration.Status.CANCELLED
        registration.save()
        self._auth_as('createstudent')

        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancelled_event_is_rejected(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.CANCELLED,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('createstudent')

        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_faculty_cannot_open_participation(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self._auth_as('facultycs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_coordinator_cannot_open_participation(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self._auth_as('hodcs')
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_fabricate_participation_for_student(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('siteadmin')
        response = self.client.post(self.url, {'event': event.id, 'student': self.student.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_open_participation(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reopening_participation_is_idempotent(self):
        """Calling 'open' twice (e.g. an offline queue retry) must return
        the same Participation row, never create a second one."""
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('createstudent')

        first = self.client.post(self.url, {'event': event.id})
        second = self.client.post(self.url, {'event': event.id})
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Participation.objects.filter(student=self.student, event=event).count(), 1)

    def test_delayed_open_after_event_date_still_succeeds(self):
        """The 'open' step does not gate on 'today == event_date' — that
        authoritative check happens per-capture against the device
        timestamp, so a legitimately delayed offline sync is never blocked
        here. This event's date is yesterday relative to 'today'."""
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department, days_until_event=-1,
            registration_starts_in=-10, registration_ends_in=-2,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('createstudent')

        response = self.client.post(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
