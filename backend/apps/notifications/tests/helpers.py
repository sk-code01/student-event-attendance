"""Fixtures for the notification tests, reusing the verified-participation
builders that already exist rather than redefining what "verified" means."""

from apps.verification.tests.helpers import (
    make_admin,
    make_college,
    make_decided_participation,
    make_department,
    make_event,
    make_faculty,
    make_event_coordinator,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
    make_verified_participation,
)

__all__ = [
    'make_admin', 'make_college', 'make_decided_participation', 'make_department', 'make_event',
    'make_faculty', 'make_event_coordinator', 'make_participation', 'make_student', 'make_submitted_evidence',
    'make_todays_published_event', 'make_verified_participation', 'DEFAULT_PASSWORD', 'AuthMixin',
]

DEFAULT_PASSWORD = 'StrongPass123!'


class AuthMixin:
    def _auth_as(self, username):
        from django.urls import reverse
        from rest_framework import status

        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
