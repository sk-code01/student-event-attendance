from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_admin, make_department, make_faculty, make_event_coordinator, make_student


class CrossRoleAccessTests(APITestCase):
    def setUp(self):
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        make_student('astudent', self.cs)
        make_faculty('afaculty', self.cs)
        make_event_coordinator('ahod', self.cs)
        make_admin('anadmin')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': 'StrongPass123!'})
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_student_cannot_provision_event_coordinator(self):
        self._auth_as('astudent')
        response = self.client.post(reverse('provision-event-coordinator'), {
            'username': 'newhod', 'email': 'newhod@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'department': self.ec.id,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_cannot_provision_event_coordinator(self):
        self._auth_as('afaculty')
        response = self.client.post(reverse('provision-event-coordinator'), {
            'username': 'newhod', 'email': 'newhod@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'department': self.ec.id,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_coordinator_cannot_provision_another_event_coordinator(self):
        self._auth_as('ahod')
        response = self.client.post(reverse('provision-event-coordinator'), {
            'username': 'newhod', 'email': 'newhod@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'department': self.ec.id,
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_provision_event_coordinator_for_department_without_one(self):
        self._auth_as('anadmin')
        response = self.client.post(reverse('provision-event-coordinator'), {
            'username': 'newhod', 'email': 'newhod@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'department': self.ec.id,
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_admin_cannot_provision_second_active_event_coordinator_for_same_department(self):
        self._auth_as('anadmin')
        response = self.client.post(reverse('provision-event-coordinator'), {
            'username': 'secondhod', 'email': 'secondhod@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'department': self.cs.id,
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('department', response.data)

    def test_unauthenticated_cannot_provision_event_coordinator(self):
        response = self.client.post(reverse('provision-event-coordinator'), {
            'username': 'newhod', 'email': 'newhod@example.com',
            'password': 'StrongPass123!', 'confirm_password': 'StrongPass123!',
            'department': self.ec.id,
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class DepartmentAccessTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        make_student('deptstudent', self.department)
        make_admin('deptadmin')

    def test_anyone_can_list_active_departments(self):
        response = self.client.get(reverse('department-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_student_cannot_create_department(self):
        login = self.client.post(
            reverse('token-obtain-pair'), {'username': 'deptstudent', 'password': 'StrongPass123!'},
        )
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        response = self.client.post(reverse('department-list'), {'name': 'Hacked Dept', 'code': 'HACK'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_department(self):
        login = self.client.post(reverse('token-obtain-pair'), {'username': 'deptadmin', 'password': 'StrongPass123!'})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
        response = self.client.post(reverse('department-list'), {'name': 'New Department', 'code': 'NEWD'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_inactive_department_is_hidden_from_public_list(self):
        make_department('OLD', 'Retired', is_active=False)
        response = self.client.get(reverse('department-list'))
        codes = [item['code'] for item in response.data['results']]
        self.assertNotIn('OLD', codes)
