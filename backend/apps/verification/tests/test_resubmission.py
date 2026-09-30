from datetime import timedelta

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import Evidence, EvidenceCapture

from .helpers import (
    iso, make_college, make_department, make_faculty, make_event_coordinator, make_participation, make_student,
    make_submitted_evidence, make_todays_published_event, make_uploaded_image, noon_on,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class ResubmissionTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.faculty = make_faculty('facultycs', self.department)
        self.student = make_student('resubstudent', self.department)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)
        self.evidence, self.version1 = make_submitted_evidence(participation=self.participation)

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def _upload_primary(self, version_id, event_date=None):
        payload = {
            'capture_role': EvidenceCapture.Role.PRIMARY,
            'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(event_date or self.event.event_date)),
            'latitude': '12.9716', 'longitude': '77.5946', 'gps_accuracy': 15,
        }
        return self.client.post(reverse('evidence-version-captures', args=[version_id]), payload, format='multipart')

    def test_cannot_open_new_version_before_resubmission_is_requested(self):
        self._auth_as('resubstudent')
        response = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_full_resubmission_flow_creates_version_2_and_preserves_version_1(self):
        self._auth_as('facultycs')
        resub = self.client.post(
            reverse('evidence-request-resubmission', args=[self.evidence.id]), {'reason': 'Face not visible'},
        )
        self.assertEqual(resub.status_code, status.HTTP_200_OK, resub.data)

        self._auth_as('resubstudent')
        open_response = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.assertEqual(open_response.status_code, status.HTTP_201_CREATED, open_response.data)
        versions = open_response.data['versions']
        self.assertEqual(len(versions), 2)
        version2 = versions[1]
        self.assertEqual(version2['version_number'], 2)
        self.assertEqual(version2['submission_reason'], 'Face not visible')

        upload = self._upload_primary(version2['id'])
        self.assertEqual(upload.status_code, status.HTTP_201_CREATED, upload.data)
        submit = self.client.post(reverse('evidence-version-submit', args=[version2['id']]))
        self.assertEqual(submit.status_code, status.HTTP_200_OK)

        self._auth_as('facultycs')
        detail = self.client.get(reverse('evidence-detail', args=[self.evidence.id]))
        self.assertEqual(len(detail.data['versions']), 2)
        v1 = detail.data['versions'][0]
        v2 = detail.data['versions'][1]
        self.assertEqual(len(v1['captures']), 1)  # version 1's capture is untouched
        self.assertEqual(v1['effective_decision'], 'RESUBMISSION_REQUIRED')
        self.assertIsNotNone(v2['submitted_at'])

        verify = self.client.post(reverse('evidence-verify', args=[self.evidence.id]), {'reason': 'looks good now'})
        self.assertEqual(verify.status_code, status.HTTP_200_OK, verify.data)
        self.assertEqual(verify.data['status'], Evidence.Status.VERIFIED)
        self.assertEqual(verify.data['current_version_number'], 2)

    def test_resubmission_capture_after_event_date_is_still_rejected(self):
        """CRITICAL rule: a resubmission does not bypass the exact-event-date
        check — a new capture whose device timestamp is not on the event
        date is rejected exactly like a first-time submission would be."""
        self._auth_as('facultycs')
        self.client.post(reverse('evidence-request-resubmission', args=[self.evidence.id]), {'reason': 'retake'})

        self._auth_as('resubstudent')
        open_response = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        version2_id = open_response.data['versions'][1]['id']

        late_timestamp = noon_on(self.event.event_date) + timedelta(days=3)
        payload = {
            'capture_role': EvidenceCapture.Role.PRIMARY,
            'image': make_uploaded_image(),
            'device_capture_timestamp': iso(late_timestamp),
            'latitude': '12.9716', 'longitude': '77.5946', 'gps_accuracy': 15,
        }
        response = self.client.post(reverse('evidence-version-captures', args=[version2_id]), payload,
                                    format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EvidenceCapture.objects.filter(evidence_version_id=version2_id).exists())

    def test_rejected_decision_does_not_allow_resubmission(self):
        """REJECTED is final for that version — only RESUBMISSION_REQUIRED
        unlocks a new version."""
        self._auth_as('facultycs')
        self.client.post(reverse('evidence-reject', args=[self.evidence.id]), {'reason': 'fabricated evidence'})

        self._auth_as('resubstudent')
        response = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_reopening_in_progress_version_is_idempotent(self):
        """Opening again before the current version is submitted just
        returns the same in-progress version — it never creates a second
        version for a mere retake before the first was ever submitted."""
        fresh_student = make_student('freshstudent', self.department)
        fresh_event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department, title='Fresh Event',
        )
        fresh_participation = make_participation(student=fresh_student, event=fresh_event)

        self._auth_as('freshstudent')
        first_open = self.client.post(reverse('evidence-list'), {'participation': fresh_participation.id})
        second_open = self.client.post(reverse('evidence-list'), {'participation': fresh_participation.id})
        self.assertEqual(first_open.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_open.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(second_open.data['versions']), 1)
        self.assertEqual(first_open.data['versions'][0]['id'], second_open.data['versions'][0]['id'])
