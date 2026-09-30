"""Phase 9 §4 — authentication hardening beyond the Phase 1 tests."""

from datetime import timedelta
from unittest import mock

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import User

from .helpers import DEFAULT_PASSWORD, AuthMixin, build_universe


class TokenHardeningTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()
        self.me = reverse('user-me')

    def _bearer(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_malformed_bearer_tokens_are_401_never_500(self):
        for garbage in ('not-a-jwt', 'a.b.c', 'eyJhbGciOiJIUzI1NiJ9.e30.', '', '   '):
            self._bearer(garbage)
            response = self.client.get(self.me)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, repr(garbage))
            self.assertNotIn('Traceback', str(response.content))

    def test_expired_access_token_is_refused(self):
        token = AccessToken.for_user(self.u.a.student)
        token.set_exp(from_time=token.current_time - timedelta(days=2), lifetime=timedelta(minutes=1))
        self._bearer(str(token))
        self.assertEqual(self.client.get(self.me).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_cannot_be_used_as_an_access_token(self):
        self._bearer(str(RefreshToken.for_user(self.u.a.student)))
        self.assertEqual(self.client.get(self.me).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_access_token_cannot_be_used_to_refresh(self):
        access = AccessToken.for_user(self.u.a.student)
        response = self.client.post(reverse('token-refresh'), {'refresh': str(access)})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_rotated_refresh_token_cannot_be_reused(self):
        login = self._auth_as('studenta')
        first = self.client.post(reverse('token-refresh'), {'refresh': login['refresh']})
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertNotEqual(first.data['refresh'], login['refresh'])
        replay = self.client.post(reverse('token-refresh'), {'refresh': login['refresh']})
        self.assertEqual(replay.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logged_out_refresh_token_is_dead(self):
        login = self._auth_as('studenta')
        self.assertEqual(self.client.post(reverse('auth-logout'), {'refresh': login['refresh']}).status_code, 205)
        response = self.client.post(reverse('token-refresh'), {'refresh': login['refresh']})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_token_of_a_deactivated_account_stops_working_immediately(self):
        login = self._auth_as('studenta')
        User.objects.filter(pk=self.u.a.student.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.me).status_code, status.HTTP_401_UNAUTHORIZED)
        refresh = self.client.post(reverse('token-refresh'), {'refresh': login['refresh']})
        self.assertEqual(refresh.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_role_claim_in_the_token_is_never_trusted(self):
        """A student whose token says STUDENT but whose account was demoted
        or promoted in the database is authorized by the database, not the
        token — and vice versa."""
        self._auth_as('facultya')
        # Faculty may list the verification queue ...
        self.assertEqual(self.client.get(reverse('evidence-list')).status_code, status.HTTP_200_OK)
        # ... until the account is changed to a student, with the same token.
        # The Faculty ID goes with the role it was issued for: the database
        # refuses to hold one on a Student row, and the Admin role-change path
        # clears it for the same reason. Clearing it here keeps this test about
        # what it is testing — that authorization follows the database, not the
        # token's claim.
        User.objects.filter(pk=self.u.a.faculty.pk).update(
            role=User.Role.STUDENT, faculty_id=None,
        )
        response = self.client.post(reverse('evidence-verify', args=[self.u.b.evidence.id]), {'reason': ''})
        self.assertIn(response.status_code, (status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND))
        me = self.client.get(self.me)
        self.assertEqual(me.data['role'], 'STUDENT')

    def test_client_supplied_role_and_department_are_ignored_at_login(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'studenta', 'password': DEFAULT_PASSWORD, 'role': 'ADMIN', 'department': 999,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        payload = AccessToken(response.data['access'])
        self.assertEqual(payload['role'], 'STUDENT')
        self.assertEqual(payload['department_id'], self.u.a.department.id)

    def test_token_verify_rejects_tampered_signature(self):
        token = str(AccessToken.for_user(self.u.a.student))
        head, body, sig = token.split('.')
        tampered = f'{head}.{body}.{"A" * len(sig)}'
        self.assertEqual(self.client.post(reverse('token-verify'), {'token': tampered}).status_code, 401)


class CredentialExposureTests(AuthMixin, APITestCase):
    """No response, from any endpoint, carries a password hash or a token
    where one is not the point of the endpoint."""

    NEEDLES = ('pbkdf2_', 'argon2', 'sha256$', '"password"', 'refresh_token', 'HTTP_AUTHORIZATION')

    def setUp(self):
        self.u = build_universe()

    def _scan(self, username, names):
        self._auth_as(username)
        for name in names:
            body = self.client.get(reverse(name)).content.decode('utf-8', 'replace')
            for needle in self.NEEDLES:
                self.assertNotIn(needle, body, f'{name} for {username} leaked {needle!r}')

    def test_admin_wide_reads_leak_no_credential_material(self):
        self._scan('sysadmin', (
            'user-me', 'registration-request-list', 'event-list', 'registration-list', 'participation-list',
            'evidence-list', 'attendance-list', 'od-request-list', 'achievement-list', 'notification-list',
            'auditlog-list', 'activity-list', 'dashboard', 'analytics-overview', 'report-types',
            'ai-anomalies', 'ai-engagement',
        ))

    def test_student_reads_leak_no_credential_material(self):
        self._scan('studenta', (
            'user-me', 'event-list', 'registration-list', 'participation-list', 'evidence-list',
            'attendance-list', 'od-request-list', 'achievement-list', 'notification-list', 'dashboard',
            'analytics-overview', 'ai-recommendations', 'ai-engagement',
        ))

    def test_login_errors_do_not_reveal_which_field_was_wrong(self):
        wrong_user = self.client.post(reverse('token-obtain-pair'), {'username': 'nobody', 'password': 'x'})
        wrong_pass = self.client.post(reverse('token-obtain-pair'), {'username': 'studenta', 'password': 'x'})
        self.assertEqual(wrong_user.status_code, wrong_pass.status_code)
        self.assertEqual(wrong_user.data, wrong_pass.data)

    def test_registration_response_carries_no_password_or_hash(self):
        response = self.client.post(reverse('auth-register'), {
            'username': 'newstudent', 'email': 'new@example.com', 'full_name': 'New Student',
            'password': 'Another$trong9', 'confirm_password': 'Another$trong9',
            'role': 'STUDENT', 'department': self.u.a.department.id,
            'university_registration_number': '1AY22MC099',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        body = response.content.decode()
        self.assertNotIn('Another$trong9', body)
        self.assertNotIn('pbkdf2', body)


class ThrottleTests(AuthMixin, APITestCase):
    """Rate limits actually fire. The test fixture clears the throttle cache
    before every test, so each test starts from a clean bucket."""

    def setUp(self):
        self.u = build_universe()

    def test_login_endpoint_is_throttled_after_ten_attempts_per_minute(self):
        url = reverse('token-obtain-pair')
        codes = [self.client.post(url, {'username': 'studenta', 'password': 'wrong'}).status_code for _ in range(11)]
        self.assertEqual(codes[:10], [status.HTTP_401_UNAUTHORIZED] * 10)
        self.assertEqual(codes[10], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_public_registration_shares_the_auth_bucket(self):
        url = reverse('auth-register')
        codes = [self.client.post(url, {}).status_code for _ in range(11)]
        self.assertEqual(codes[10], status.HTTP_429_TOO_MANY_REQUESTS)

    def test_ai_endpoints_have_their_own_tighter_scope(self):
        self._auth_as('sysadmin')
        with mock.patch.dict('rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES', {'ai': '2/min'}):
            codes = [self.client.get(reverse('ai-engagement')).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, status.HTTP_429_TOO_MANY_REQUESTS])

    def test_report_export_has_its_own_scope(self):
        self._auth_as('sysadmin')
        url = reverse('report-export', args=['system'])
        with mock.patch.dict('rest_framework.throttling.ScopedRateThrottle.THROTTLE_RATES', {'reports': '2/min'}):
            codes = [self.client.get(url, {'file_format': 'csv'}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, status.HTTP_429_TOO_MANY_REQUESTS])

    def test_throttle_scopes_are_configured(self):
        from django.conf import settings
        rates = settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']
        for scope in ('anon', 'user', 'auth', 'ai', 'reports'):
            self.assertIn(scope, rates)
