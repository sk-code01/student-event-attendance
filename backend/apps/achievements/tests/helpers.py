"""Test fixtures for the achievements workflow."""

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
    'achievement_payload',
]

DEFAULT_PASSWORD = 'StrongPass123!'


def achievement_payload(participation, **overrides):
    """A valid create payload. `achievement_date` defaults to the event date,
    which is always both >= the event date and <= today for the
    today's-event fixtures used throughout these tests."""
    payload = {
        'participation': participation.id,
        'title': 'First Place',
        'description': 'Won the coding contest.',
        'achievement_type': 'Competition',
        'achievement_date': str(participation.event.event_date),
    }
    payload.update(overrides)
    return payload


class AuthMixin:
    def _auth_as(self, username):
        from django.urls import reverse
        from rest_framework import status

        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')
