from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import make_department, make_student


class LogoutTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        make_student('logoutuser', self.department)
        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'logoutuser', 'password': 'StrongPass123!',
        })
        self.access = login.data['access']
        self.refresh = login.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')

    def test_logout_blacklists_refresh_token(self):
        response = self.client.post(reverse('auth-logout'), {'refresh': self.refresh})
        self.assertEqual(response.status_code, status.HTTP_205_RESET_CONTENT)

        self.client.credentials()
        retry = self.client.post(reverse('token-refresh'), {'refresh': self.refresh})
        self.assertEqual(retry.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_requires_authentication(self):
        self.client.credentials()
        response = self.client.post(reverse('auth-logout'), {'refresh': self.refresh})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_without_refresh_token_is_rejected(self):
        response = self.client.post(reverse('auth-logout'), {})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ChangePasswordTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.user = make_student('pwuser', self.department)
        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'pwuser', 'password': 'StrongPass123!',
        })
        self.access = login.data['access']
        self.refresh = login.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.access}')

    def test_change_password_requires_correct_old_password(self):
        response = self.client.post(reverse('user-change-password'), {
            'old_password': 'WrongOldPassword!',
            'new_password': 'NewStrongPass456!',
            'confirm_new_password': 'NewStrongPass456!',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_rejects_mismatched_confirmation(self):
        response = self.client.post(reverse('user-change-password'), {
            'old_password': 'StrongPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_new_password': 'Different789!',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_change_password_rejects_weak_new_password(self):
        response = self.client.post(reverse('user-change-password'), {
            'old_password': 'StrongPass123!',
            'new_password': '12345678',
            'confirm_new_password': '12345678',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_successful_password_change_does_not_leak_password_in_response(self):
        response = self.client.post(reverse('user-change-password'), {
            'old_password': 'StrongPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_new_password': 'NewStrongPass456!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn('NewStrongPass456!', str(response.data))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewStrongPass456!'))

    def test_password_change_blacklists_existing_refresh_tokens(self):
        self.client.post(reverse('user-change-password'), {
            'old_password': 'StrongPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_new_password': 'NewStrongPass456!',
        })
        self.client.credentials()
        retry = self.client.post(reverse('token-refresh'), {'refresh': self.refresh})
        self.assertEqual(retry.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_can_login_with_new_password_after_change(self):
        self.client.post(reverse('user-change-password'), {
            'old_password': 'StrongPass123!',
            'new_password': 'NewStrongPass456!',
            'confirm_new_password': 'NewStrongPass456!',
        })
        self.client.credentials()
        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'pwuser', 'password': 'NewStrongPass456!',
        })
        self.assertEqual(login.status_code, status.HTTP_200_OK)
