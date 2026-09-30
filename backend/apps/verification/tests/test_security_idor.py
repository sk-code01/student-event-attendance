from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import Evidence, EvidenceVerification, EvidenceVersion

from .helpers import (
    iso, make_admin, make_college, make_department, make_faculty, make_event_coordinator, make_participation,
    make_student,
    make_submitted_evidence, make_todays_published_event, make_uploaded_image, noon_on,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class EvidenceIdorTests(APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')
        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.admin = make_admin('siteadmin')

        self.student_a = make_student('studenta', self.cs)
        self.student_b = make_student('studentb', self.cs)

        self.event = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
        )
        self.participation_b = make_participation(student=self.student_b, event=self.event)
        self.evidence_b, self.version_b = make_submitted_evidence(participation=self.participation_b)

        self.detail_url = reverse('evidence-detail', args=[self.evidence_b.id])
        self.image_url = reverse('evidence-capture-image', args=[self.version_b.captures.first().id])

    def _auth_as(self, username):
        login = self.client.post(reverse('token-obtain-pair'), {'username': username, 'password': DEFAULT_PASSWORD})
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

    def test_student_cannot_view_another_students_evidence(self):
        self._auth_as('studenta')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_student_cannot_view_another_students_capture_image(self):
        self._auth_as('studenta')
        response = self.client.get(self.image_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_own_capture_image_is_accessible(self):
        self._auth_as('studentb')
        response = self.client.get(self.image_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_faculty_other_department_gets_404_not_403(self):
        """Outside the requester's visible queryset -> 404 (never confirming
        existence), matching the convention used everywhere else."""
        self._auth_as('facultyec')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_own_department_faculty_gets_200(self):
        self._auth_as('facultycs')
        response = self.client.get(self.detail_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_student_cannot_open_capture_upload_for_a_version_they_do_not_own(self):
        self._auth_as('studenta')
        payload = {
            'capture_role': 'ADDITIONAL', 'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(self.event.event_date)),
            'latitude': '1', 'longitude': '1', 'gps_accuracy': 10,
        }
        response = self.client.post(
            reverse('evidence-version-captures', args=[self.version_b.id]), payload, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_faculty_cannot_upload_a_capture(self):
        self._auth_as('facultycs')
        payload = {
            'capture_role': 'ADDITIONAL', 'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(self.event.event_date)),
            'latitude': '1', 'longitude': '1', 'gps_accuracy': 10,
        }
        response = self.client.post(
            reverse('evidence-version-captures', args=[self.version_b.id]), payload, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_submit_a_version_they_do_not_own(self):
        self._auth_as('studenta')
        response = self.client.post(reverse('evidence-version-submit', args=[self.version_b.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_client_cannot_set_verification_status_directly(self):
        """There is no endpoint accepting a raw `status` field — decisions
        only ever happen through verify/reject/request-resubmission, so a
        client-supplied status in the request body is simply ignored."""
        self._auth_as('facultycs')
        response = self.client.post(
            reverse('evidence-verify', args=[self.evidence_b.id]), {'status': 'REJECTED', 'reason': 'ignored anyway'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], Evidence.Status.VERIFIED)

    def test_client_cannot_spoof_reviewer_identity(self):
        """The reviewer is always request.user — a client-supplied
        `reviewer`/`reviewer_id` field in the body is never honored."""
        self._auth_as('facultycs')
        response = self.client.post(
            reverse('evidence-verify', args=[self.evidence_b.id]), {'reviewer': self.event_coordinator_cs.id,
                                                                    'reviewer_id': self.event_coordinator_cs.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        verification = EvidenceVerification.objects.get(evidence_version=self.version_b)
        self.assertEqual(verification.reviewer_id, self.faculty_cs.id)

    def test_client_cannot_spoof_version_number(self):
        self._auth_as('facultycs')
        self.client.post(reverse('evidence-request-resubmission', args=[self.evidence_b.id]), {'reason': 'retake'})
        self._auth_as('studentb')
        response = self.client.post(
            reverse('evidence-list'), {'participation': self.participation_b.id, 'version_number': 99},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_version = EvidenceVersion.objects.filter(evidence=self.evidence_b).order_by('-version_number').first()
        self.assertEqual(new_version.version_number, 2)

    def test_client_cannot_spoof_server_received_timestamp_on_capture(self):
        self._auth_as('facultycs')
        self.client.post(reverse('evidence-request-resubmission', args=[self.evidence_b.id]), {'reason': 'retake'})
        self._auth_as('studentb')
        open_response = self.client.post(reverse('evidence-list'), {'participation': self.participation_b.id})
        version2_id = open_response.data['versions'][1]['id']

        spoofed = iso(timezone.now() - timedelta(days=365))
        payload = {
            'capture_role': 'PRIMARY', 'image': make_uploaded_image(),
            'device_capture_timestamp': iso(noon_on(self.event.event_date)),
            'server_received_timestamp': spoofed,
            'latitude': '1', 'longitude': '1', 'gps_accuracy': 10,
        }
        response = self.client.post(reverse('evidence-version-captures', args=[version2_id]), payload,
                                    format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertNotEqual(response.data['server_received_timestamp'][:4], spoofed[:4])
