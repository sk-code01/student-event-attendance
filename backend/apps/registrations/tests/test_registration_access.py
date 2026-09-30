from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event

from .helpers import (
    make_admin, make_college, make_department, make_event, make_faculty, make_event_coordinator, make_registration,
    make_student,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class RegistrationAccessTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.admin = make_admin('siteadmin')
        self.faculty = make_faculty('facultycs', self.cs)
        self.student_cs = make_student('studentcs', self.cs)
        self.student_ec = make_student('studentec', self.ec)

        self.event_cs = make_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
            status=Event.Status.PUBLISHED,
        )
        self.event_ec = make_event(
            created_by=self.event_coordinator_ec, college=self.college, department=self.ec,
            status=Event.Status.PUBLISHED,
        )
        self.reg_cs = make_registration(student=self.student_cs, event=self.event_cs)
        self.reg_ec = make_registration(student=self.student_ec, event=self.event_ec)

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_student_sees_only_own_registrations(self):
        self._auth_as('studentcs')
        response = self.client.get(reverse('registration-list'))
        ids = {item['id'] for item in response.data['results']}
        self.assertEqual(ids, {self.reg_cs.id})

    def test_student_cannot_retrieve_another_students_registration(self):
        self._auth_as('studentcs')
        response = self.client.get(reverse('registration-detail', args=[self.reg_ec.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_coordinator_sees_only_own_department_registrations(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('registration-list'))
        ids = {item['id'] for item in response.data['results']}
        self.assertEqual(ids, {self.reg_cs.id})

    def test_event_coordinator_cannot_retrieve_other_department_registration(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('registration-detail', args=[self.reg_ec.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_sees_all_registrations(self):
        self._auth_as('siteadmin')
        response = self.client.get(reverse('registration-list'))
        ids = {item['id'] for item in response.data['results']}
        self.assertEqual(ids, {self.reg_cs.id, self.reg_ec.id})

    def test_faculty_sees_their_own_departments_registrations(self):
        # This replaced the earlier placeholder, where Faculty had no
        # registration scope at all. Faculty verify evidence for their
        # department's events, so they need to see who registered for them;
        # what separates them from the Event Coordinator is what they may do,
        # not what they may see.
        self._auth_as('facultycs')
        response = self.client.get(reverse('registration-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        ids = {item['id'] for item in response.data['results']}
        self.assertEqual(ids, {self.reg_cs.id})
        self.assertNotIn(self.reg_ec.id, ids)

    def test_unauthenticated_cannot_list_registrations(self):
        response = self.client.get(reverse('registration-list'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_event_coordinator_can_filter_registrations_by_event(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('registration-list'), {'event': self.event_cs.id})
        ids = {item['id'] for item in response.data['results']}
        self.assertEqual(ids, {self.reg_cs.id})

    def test_idor_attempt_on_registration_detail_by_id_guessing(self):
        # A student who never registered for event_ec should not be able to
        # view reg_ec's details just by guessing/incrementing its numeric id.
        self._auth_as('studentcs')
        response = self.client.get(reverse('registration-detail', args=[self.reg_ec.id]))
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
