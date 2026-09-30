import jwt
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_department, make_student, make_user


class LoginTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.student = make_student('validstudent', self.department)

    def test_login_with_valid_credentials_returns_tokens(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'validstudent', 'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

    def test_access_token_carries_role_and_department_claims(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'validstudent', 'password': 'StrongPass123!',
        })
        decoded = jwt.decode(response.data['access'], options={'verify_signature': False})
        self.assertEqual(decoded['role'], 'STUDENT')
        self.assertEqual(decoded['department_id'], self.department.id)

    def test_wrong_password_returns_generic_invalid_credentials(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'validstudent', 'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_username_returns_generic_invalid_credentials(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'doesnotexist', 'password': 'WrongPassword!',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_deactivated_account_gets_inactive_message(self):
        make_user('deactivated', department=self.department, is_active=False)
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'deactivated', 'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('deactivated', str(response.data).lower())

    def test_login_does_not_ask_for_or_accept_a_role_selector(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'validstudent', 'password': 'StrongPass123!', 'role': 'ADMIN',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        decoded = jwt.decode(response.data['access'], options={'verify_signature': False})
        self.assertEqual(decoded['role'], 'STUDENT')


class RefreshAndVerifyTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        make_student('refreshuser', self.department)
        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'refreshuser', 'password': 'StrongPass123!',
        })
        self.access = login.data['access']
        self.refresh = login.data['refresh']

    def test_refresh_token_returns_new_access_token(self):
        response = self.client.post(reverse('token-refresh'), {'refresh': self.refresh})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)

    def test_verify_valid_access_token(self):
        response = self.client.post(reverse('token-verify'), {'token': self.access})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_verify_garbage_token_fails(self):
        response = self.client.post(reverse('token-verify'), {'token': 'not-a-real-token'})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class CurrentUserTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        make_student('meuser', self.department)
        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'meuser', 'password': 'StrongPass123!',
        })
        self.access = login.data['access']

    def test_me_endpoint_returns_current_user_without_password(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')
        response = self.client.get(reverse('user-me'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'meuser')
        self.assertEqual(response.data['role'], 'STUDENT')
        self.assertNotIn('password', response.data)

    def test_me_endpoint_requires_authentication(self):
        response = self.client.get(reverse('user-me'))
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
