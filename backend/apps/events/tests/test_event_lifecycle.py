from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event

from .helpers import make_admin, make_college, make_department, make_event, make_event_coordinator

DEFAULT_PASSWORD = 'StrongPass123!'


class EventLifecycleTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.admin = make_admin('siteadmin')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_publish_draft_event(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('hodcs')
        response = self.client.post(reverse('event-publish', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_cannot_publish_already_published_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('hodcs')
        response = self.client.post(reverse('event-publish', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_publish_cancelled_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.CANCELLED,
        )
        self._auth_as('hodcs')
        response = self.client.post(reverse('event-publish', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cancel_published_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('hodcs')
        response = self.client.post(reverse('event-cancel', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.CANCELLED)

    def test_cancel_draft_event_is_allowed(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('hodcs')
        response = self.client.post(reverse('event-cancel', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cannot_cancel_already_cancelled_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.CANCELLED,
        )
        self._auth_as('hodcs')
        response = self.client.post(reverse('event-cancel', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_edit_cancelled_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.CANCELLED,
        )
        self._auth_as('hodcs')
        response = self.client.patch(reverse('event-detail', args=[event.id]), {'title': 'New Title'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_edit_completed_event(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
            status=Event.Status.COMPLETED,
        )
        self._auth_as('hodcs')
        response = self.client.patch(reverse('event-detail', args=[event.id]), {'title': 'New Title'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_can_edit_draft_event(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('hodcs')
        response = self.client.patch(reverse('event-detail', args=[event.id]), {'title': 'Updated Title'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        event.refresh_from_db()
        self.assertEqual(event.title, 'Updated Title')

    def test_event_coordinator_cannot_edit_event_in_other_department(self):
        # A DRAFT event in another department is outside this Event Coordinator's visible
        # queryset entirely (see test_event_visibility), so the API
        # correctly returns 404 rather than 403 — it never confirms the
        # event's existence to an Event Coordinator who isn't authorized to see it.
        other_dept = make_department('EC', 'Electronics')
        other_event_coordinator = make_event_coordinator('hodec', other_dept)
        event = make_event(created_by=other_event_coordinator, college=self.college, department=other_dept)
        self._auth_as('hodcs')
        response = self.client.patch(reverse('event-detail', args=[event.id]), {'title': 'Hijacked'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        event.refresh_from_db()
        self.assertNotEqual(event.title, 'Hijacked')

    def test_event_coordinator_cannot_edit_published_event_in_other_department(self):
        # A PUBLISHED event IS visible cross-department (browsable), so here
        # the object is found and the object-level permission is what
        # correctly rejects the edit with 403.
        other_dept = make_department('EC', 'Electronics')
        other_event_coordinator = make_event_coordinator('hodec', other_dept)
        event = make_event(
            created_by=other_event_coordinator, college=self.college, department=other_dept,
            status=Event.Status.PUBLISHED,
        )
        self._auth_as('hodcs')
        response = self.client.patch(reverse('event-detail', args=[event.id]), {'title': 'Hijacked'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        event.refresh_from_db()
        self.assertNotEqual(event.title, 'Hijacked')

    def test_admin_can_edit_any_department_event(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('siteadmin')
        response = self.client.patch(reverse('event-detail', args=[event.id]), {'title': 'Admin Edit'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_admin_can_delete_event_without_registrations(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('siteadmin')
        response = self.client.delete(reverse('event-detail', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(id=event.id).exists())

    def test_event_coordinator_cannot_delete_event(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, department=self.department)
        self._auth_as('hodcs')
        response = self.client.delete(reverse('event-detail', args=[event.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Event.objects.filter(id=event.id).exists())
