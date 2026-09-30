from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.events.models import Event

from .helpers import make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_student

DEFAULT_PASSWORD = 'StrongPass123!'


class EventCreationTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.admin = make_admin('siteadmin')
        self.faculty = make_faculty('facultycs', self.department)
        self.student = make_student('studentcs', self.department)
        self.url = reverse('event-list')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def _payload(self, **overrides):
        from datetime import timedelta
        from django.utils import timezone
        today = timezone.localdate()
        payload = {
            'title': 'Annual Tech Fest',
            'description': 'A technical festival.',
            'event_date': str(today + timedelta(days=20)),
            'venue': 'Main Hall',
            'category': 'Technical',
            'conducting_college': self.college.id,
            'registration_start_date': str(today + timedelta(days=1)),
            'registration_end_date': str(today + timedelta(days=15)),
        }
        payload.update(overrides)
        return payload

    def test_event_coordinator_can_create_event(self):
        self._auth_as('hodcs')
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        event = Event.objects.get(id=response.data['id'])
        self.assertEqual(event.created_by_id, self.event_coordinator.id)
        self.assertEqual(event.department_id, self.department.id)
        self.assertEqual(event.status, Event.Status.DRAFT)

    def test_admin_can_create_event(self):
        self._auth_as('siteadmin')
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        event = Event.objects.get(id=response.data['id'])
        self.assertEqual(event.created_by_id, self.admin.id)
        self.assertIsNone(event.department_id)

    def test_student_cannot_create_event(self):
        self._auth_as('studentcs')
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(Event.objects.filter(title='Annual Tech Fest').exists())

    def test_faculty_cannot_create_event(self):
        self._auth_as('facultycs')
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_create_event(self):
        response = self.client.post(self.url, self._payload())
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_client_cannot_set_status_created_by_or_department(self):
        self._auth_as('hodcs')
        other_dept = make_department('EC', 'Electronics')
        response = self.client.post(self.url, self._payload(
            status=Event.Status.PUBLISHED, created_by=self.admin.id, department=other_dept.id,
        ))
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        event = Event.objects.get(id=response.data['id'])
        self.assertEqual(event.status, Event.Status.DRAFT)
        self.assertEqual(event.created_by_id, self.event_coordinator.id)
        self.assertEqual(event.department_id, self.department.id)

    def test_registration_end_after_event_date_is_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        today = timezone.localdate()
        self._auth_as('hodcs')
        response = self.client.post(self.url, self._payload(
            event_date=str(today + timedelta(days=5)),
            registration_end_date=str(today + timedelta(days=5)),
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('registration_end_date', response.data)

    def test_registration_start_after_end_is_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        today = timezone.localdate()
        self._auth_as('hodcs')
        response = self.client.post(self.url, self._payload(
            registration_start_date=str(today + timedelta(days=10)),
            registration_end_date=str(today + timedelta(days=5)),
        ))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('registration_start_date', response.data)

    def test_short_title_is_rejected(self):
        self._auth_as('hodcs')
        response = self.client.post(self.url, self._payload(title='AB'))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('title', response.data)

    def test_invalid_college_is_rejected(self):
        self._auth_as('hodcs')
        response = self.client.post(self.url, self._payload(conducting_college=999999))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('conducting_college', response.data)

    def test_inactive_college_is_not_selectable(self):
        inactive_college = make_college(code='OLD', name='Old College', is_active=False)
        self._auth_as('hodcs')
        response = self.client.post(self.url, self._payload(conducting_college=inactive_college.id))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('conducting_college', response.data)
