from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog
from apps.participation.models import Participation
from apps.verification.models import EvidenceCapture

from .helpers import (
    iso, make_college, make_department, make_event_coordinator, make_participation, make_student,
    make_todays_published_event,
    make_uploaded_image, noon_on,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class SubmitTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.student = make_student('submitstudent', self.department)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)

        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'submitstudent', 'password': DEFAULT_PASSWORD,
        })
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

        open_response = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.version_id = open_response.data['versions'][0]['id']
        self.capture_url = reverse('evidence-version-captures', args=[self.version_id])
        self.submit_url = reverse('evidence-version-submit', args=[self.version_id])

    def _upload_primary(self):
        payload = {
            'capture_role': EvidenceCapture.Role.PRIMARY,
            'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(self.event.event_date)),
            'latitude': '12.9716', 'longitude': '77.5946', 'gps_accuracy': 15,
        }
        return self.client.post(self.capture_url, payload, format='multipart')

    def test_cannot_submit_without_primary_capture(self):
        response = self.client.post(self.submit_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submit_succeeds_with_primary_capture(self):
        self._upload_primary()
        response = self.client.post(self.submit_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIsNotNone(response.data['submitted_at'])

        self.participation.refresh_from_db()
        self.assertEqual(self.participation.status, Participation.Status.SUBMITTED)
        self.assertIsNotNone(self.participation.submitted_at)

    def test_duplicate_submit_is_idempotent(self):
        self._upload_primary()
        first = self.client.post(self.submit_url)
        second = self.client.post(self.submit_url)
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(first.data['submitted_at'], second.data['submitted_at'])

    def test_submission_audit_log_recorded_without_sensitive_content(self):
        self._upload_primary()
        self.client.post(self.submit_url)

        actions = list(AuditLog.objects.filter(actor=self.student).values_list('action', flat=True))
        self.assertIn('EVIDENCE_SUBMITTED', actions)
        for entry in AuditLog.objects.filter(actor=self.student):
            self.assertNotIn('image', entry.description.lower())
            self.assertNotIn('token', entry.description.lower())

    def test_full_open_capture_submit_flow_logs_created_and_submitted(self):
        actions = list(AuditLog.objects.filter(actor=self.student).values_list('action', flat=True))
        self.assertIn('EVIDENCE_CREATED', actions)

        self._upload_primary()
        self.client.post(self.submit_url)
        actions = list(AuditLog.objects.filter(actor=self.student).values_list('action', flat=True))
        self.assertIn('EVIDENCE_SUBMITTED', actions)
