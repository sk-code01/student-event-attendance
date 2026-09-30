from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event

from .helpers import (
    make_admin, make_college, make_department, make_event, make_faculty, make_event_coordinator, make_student,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class EventVisibilityTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.admin = make_admin('siteadmin')
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('studentcs', self.cs)

        self.cs_draft = make_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs, title='CS Draft',
        )
        self.cs_published = make_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
            title='CS Published', status=Event.Status.PUBLISHED,
        )
        self.ec_draft = make_event(
            created_by=self.event_coordinator_ec, college=self.college, department=self.ec, title='EC Draft',
        )
        self.ec_published = make_event(
            created_by=self.event_coordinator_ec, college=self.college, department=self.ec,
            title='EC Published', status=Event.Status.PUBLISHED,
        )

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def _titles(self, response):
        return {item['title'] for item in response.data['results']}

    def test_student_never_sees_draft_events(self):
        self._auth_as('studentcs')
        response = self.client.get(reverse('event-list'))
        titles = self._titles(response)
        self.assertNotIn('CS Draft', titles)
        self.assertNotIn('EC Draft', titles)
        self.assertIn('CS Published', titles)
        self.assertIn('EC Published', titles)

    def test_faculty_never_sees_draft_events(self):
        self._auth_as('facultycs')
        response = self.client.get(reverse('event-list'))
        titles = self._titles(response)
        self.assertNotIn('CS Draft', titles)
        self.assertNotIn('EC Draft', titles)

    def test_event_coordinator_sees_own_department_drafts_and_other_departments_published(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('event-list'))
        titles = self._titles(response)
        self.assertIn('CS Draft', titles)
        self.assertIn('CS Published', titles)
        self.assertIn('EC Published', titles)
        self.assertNotIn('EC Draft', titles)

    def test_admin_sees_all_events_including_all_drafts(self):
        self._auth_as('siteadmin')
        response = self.client.get(reverse('event-list'))
        titles = self._titles(response)
        self.assertEqual(titles, {'CS Draft', 'CS Published', 'EC Draft', 'EC Published'})

    def test_student_cannot_retrieve_draft_event_directly(self):
        self._auth_as('studentcs')
        response = self.client.get(reverse('event-detail', args=[self.cs_draft.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_cannot_list_events(self):
        response = self.client.get(reverse('event-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
