"""Phase 0 regression coverage, carried forward unchanged in spirit: the
health endpoint and basic JWT issuance must keep working exactly as before
Phase 1 layered role/department/approval logic on top."""

from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class HealthCheckTests(APITestCase):
    def test_health_check_is_publicly_accessible(self):
        response = self.client.get(reverse('health-check'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ok')
        self.assertEqual(response.data['database'], 'ok')


class BasicJWTRegressionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='carol', email='carol@example.com', password='StrongPass123!',
        )

    def test_obtain_and_refresh_token(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'carol',
            'password': 'StrongPass123!',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        refresh_response = self.client.post(reverse('token-refresh'), {
            'refresh': response.data['refresh'],
        })
        self.assertEqual(refresh_response.status_code, status.HTTP_200_OK)
        self.assertIn('access', refresh_response.data)

    def test_invalid_credentials_are_rejected(self):
        response = self.client.post(reverse('token-obtain-pair'), {
            'username': 'carol',
            'password': 'wrong-password',
        })
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ReadinessCheckTests(APITestCase):
    """Phase 10 §11 — readiness is distinct from liveness: it fails (503) when
    a dependency is down, so a proxy can stop routing traffic, while the
    liveness probe stays 200 so a transient database blip never restarts a
    healthy process."""

    def test_readiness_is_publicly_accessible_and_reports_ready(self):
        response = self.client.get(reverse('readiness-check'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ready')
        self.assertEqual(response.data['checks']['database'], 'ok')

    def test_readiness_returns_503_when_the_database_is_unreachable(self):
        with mock.patch('config.views._database_reachable', return_value=False):
            response = self.client.get(reverse('readiness-check'))
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['status'], 'not-ready')
        self.assertEqual(response.data['checks']['database'], 'unavailable')

    def test_liveness_stays_200_when_the_database_is_unreachable(self):
        with mock.patch('config.views._database_reachable', return_value=False):
            response = self.client.get(reverse('health-check'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'ok')
        self.assertEqual(response.data['database'], 'unavailable')

    def test_probes_never_leak_configuration(self):
        for name in ('health-check', 'readiness-check'):
            body = self.client.get(reverse(name)).content.decode()
            for secret in (settings.SECRET_KEY, str(settings.DATABASES['default'].get('PASSWORD') or 'x' * 40),
                           str(settings.DATABASES['default'].get('HOST') or 'y' * 40)):
                self.assertNotIn(secret, body, name)
            self.assertNotIn('Traceback', body, name)
