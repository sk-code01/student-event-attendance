from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.tests.helpers import make_admin, make_department, make_student
from apps.colleges.models import College

DEFAULT_PASSWORD = 'StrongPass123!'


class CollegeAccessTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.student = make_student('collegestudent', self.department)
        self.admin = make_admin('collegeadmin')

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_anyone_can_list_active_colleges(self):
        College.objects.create(name='Engineering College', code='ENGG')
        response = self.client.get(reverse('college-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_inactive_college_is_hidden_from_public_list(self):
        College.objects.create(name='Retired College', code='OLD', is_active=False)
        response = self.client.get(reverse('college-list'))
        codes = [item['code'] for item in response.data['results']]
        self.assertNotIn('OLD', codes)

    def test_student_cannot_create_college(self):
        self._auth_as('collegestudent')
        response = self.client.post(reverse('college-list'), {'name': 'Hacked College', 'code': 'HACK'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_create_college(self):
        self._auth_as('collegeadmin')
        response = self.client.post(reverse('college-list'), {'name': 'New College', 'code': 'NEWC'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
