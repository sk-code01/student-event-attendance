from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.participation.models import Participation

from .helpers import (
    make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_registration, make_student,
    make_todays_published_event,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class ParticipationIdorTests(APITestCase):
    """Capture/image/submit IDOR coverage moved to
    apps.verification.tests (those endpoints no longer live on
    Participation as of Phase 4) — this file keeps only the
    Participation-open/view IDOR cases that are still exercised here."""

    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.admin = make_admin('siteadmin')
        self.faculty = make_faculty('facultycs', self.cs)

        self.student_a = make_student('studenta', self.cs)
        self.student_b = make_student('studentb', self.cs)

        self.event = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
        )
        self.registration_a = make_registration(student=self.student_a, event=self.event)
        self.registration_b = make_registration(student=self.student_b, event=self.event)

        self.participation_b = Participation.objects.create(registration=self.registration_b)

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_student_cannot_view_another_students_participation(self):
        self._auth_as('studenta')
        response = self.client.get(reverse('participation-detail', args=[self.participation_b.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_coordinator_can_view_own_department_participation(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('participation-detail', args=[self.participation_b.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_event_coordinator_from_other_department_cannot_view_participation(self):
        self._auth_as('hodec')
        response = self.client.get(reverse('participation-detail', args=[self.participation_b.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_view_any_participation_but_cannot_create_one_for_a_student(self):
        self._auth_as('siteadmin')
        get_response = self.client.get(reverse('participation-detail', args=[self.participation_b.id]))
        self.assertEqual(get_response.status_code, status.HTTP_200_OK)

        post_response = self.client.post(reverse('participation-list'), {'event': self.event.id})
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_cannot_view_or_create_participation(self):
        self._auth_as('facultycs')
        list_response = self.client.get(reverse('participation-list'))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data['results'], [])

        create_response = self.client.post(reverse('participation-list'), {'event': self.event.id})
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_submit_using_another_students_registration_id(self):
        """Attempt to open a participation by supplying another student's
        registration in the request — the view never accepts a
        client-supplied registration id at all, only an event id, and the
        registration is always looked up server-side for request.user."""
        self._auth_as('studenta')
        response = self.client.post(reverse('participation-list'), {
            'event': self.event.id, 'registration': self.registration_b.id, 'student': self.student_b.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        participation = Participation.objects.get(id=response.data['id'])
        self.assertEqual(participation.student_id, self.student_a.id)
        self.assertEqual(participation.registration_id, self.registration_a.id)
