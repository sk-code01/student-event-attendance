"""The backend remains the authority over a session (requirement 36.8).

Whatever the Angular application does with its own state, a token that has
expired, been rotated away or been blacklisted must not open a protected
endpoint. These tests exercise that from the outside, the way a user who had
edited their browser storage would.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .helpers import DEFAULT_PASSWORD, make_department, make_student


class SessionBoundaryTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.student = make_student('stu1', self.department)
        self.protected = reverse('user-me')

    def _authenticate(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def _login(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'stu1', 'password': DEFAULT_PASSWORD,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['access'], response.data['refresh']

    def test_a_valid_access_token_opens_a_protected_endpoint(self):
        access, _ = self._login()
        self._authenticate(access)

        self.assertEqual(self.client.get(self.protected).status_code, status.HTTP_200_OK)

    def test_an_expired_access_token_is_refused(self):
        token = AccessToken.for_user(self.student)
        # Moved into the past rather than waited for: the rule is the claim,
        # not the clock this test happens to run on.
        token.set_exp(from_time=timezone.now() - timedelta(hours=2), lifetime=timedelta(minutes=1))
        self._authenticate(str(token))

        self.assertEqual(self.client.get(self.protected).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_blacklisted_refresh_token_cannot_mint_a_new_access_token(self):
        access, refresh = self._login()
        self._authenticate(access)
        self.client.post(reverse('auth-logout'), {'refresh': refresh}, format='json')

        # This is the state after an explicit logout: the client may still hold
        # the string, but it is worthless.
        self.client.credentials()
        response = self.client.post(reverse('token-refresh'), {'refresh': refresh}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_rotated_refresh_token_cannot_be_reused(self):
        _, refresh = self._login()
        first = self.client.post(reverse('token-refresh'), {'refresh': refresh}, format='json')
        self.assertEqual(first.status_code, status.HTTP_200_OK, first.data)

        # Rotation blacklists the old token, so replaying it is refused even
        # though it has not expired.
        replay = self.client.post(reverse('token-refresh'), {'refresh': refresh}, format='json')
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_an_expired_refresh_token_is_refused(self):
        token = RefreshToken.for_user(self.student)
        token.set_exp(from_time=timezone.now() - timedelta(days=30), lifetime=timedelta(days=1))

        response = self.client.post(reverse('token-refresh'), {'refresh': str(token)}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_tampered_token_is_refused(self):
        access, _ = self._login()
        head, payload, signature = access.split('.')
        self._authenticate(f'{head}.{payload}.{signature[:-2]}xx')

        self.assertEqual(self.client.get(self.protected).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_a_deactivated_account_loses_access_with_its_token_still_in_hand(self):
        access, _ = self._login()
        self.student.is_active = False
        self.student.save(update_fields=['is_active'])
        self._authenticate(access)

        # Authorization follows the database, not the token the client holds.
        self.assertEqual(self.client.get(self.protected).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_no_protected_endpoint_answers_without_a_token(self):
        # The frontend clearing its own state is not what protects these; this
        # is.
        for name in ('user-me', 'notification-list', 'registration-list'):
            with self.subTest(endpoint=name):
                self.client.credentials()
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
