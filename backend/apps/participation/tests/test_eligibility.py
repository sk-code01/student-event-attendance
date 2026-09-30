from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event
from apps.registrations.models import Registration

from .helpers import (
    make_college, make_department, make_event_coordinator, make_registration, make_student, make_todays_published_event,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class EligibilityTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.student = make_student('eligstudent', self.department)
        self.url = reverse('participation-eligibility')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_eligible_when_registered_for_todays_event(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['eligible'])
        self.assertIsNone(response.data['reason'])

    def test_not_eligible_without_registration(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertFalse(response.data['eligible'])
        self.assertIn('not registered', response.data['reason'])

    def test_not_eligible_for_cancelled_registration(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        registration = make_registration(student=self.student, event=event)
        registration.status = Registration.Status.CANCELLED
        registration.save()
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertFalse(response.data['eligible'])

    def test_not_eligible_for_cancelled_event(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.CANCELLED,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertFalse(response.data['eligible'])
        self.assertIn('cancelled', response.data['reason'])

    def test_not_eligible_when_not_event_date(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department, days_until_event=3,
        )
        make_registration(student=self.student, event=event)
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertFalse(response.data['eligible'])
        self.assertIn('event date', response.data['reason'])

    def test_not_eligible_when_already_submitted(self):
        from django.utils import timezone

        from apps.participation.models import Participation

        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        registration = make_registration(student=self.student, event=event)
        Participation.objects.create(
            registration=registration, status=Participation.Status.SUBMITTED, submitted_at=timezone.now(),
        )
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertFalse(response.data['eligible'])
        self.assertIn('already submitted', response.data['reason'])

    def test_still_eligible_to_retry_when_a_draft_participation_has_no_successful_submission(self):
        """A DRAFT Participation with no captures (e.g. its only upload
        attempt was rejected for bad GPS accuracy) must not permanently
        lock the student out — they need to be able to retry."""
        from apps.participation.models import Participation

        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        registration = make_registration(student=self.student, event=event)
        Participation.objects.create(registration=registration)  # status defaults to DRAFT
        self._auth_as('eligstudent')

        response = self.client.get(self.url, {'event': event.id})
        self.assertTrue(response.data['eligible'])
        self.assertIsNone(response.data['reason'])

    def test_non_student_cannot_check_eligibility(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self._auth_as('hodcs')
        response = self.client.get(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_check_eligibility(self):
        event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        response = self.client.get(self.url, {'event': event.id})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
