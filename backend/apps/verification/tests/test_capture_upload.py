from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import EvidenceCapture

from .helpers import (
    iso, make_college, make_department, make_event_coordinator, make_participation, make_student,
    make_todays_published_event,
    make_uploaded_image, noon_on,
)

DEFAULT_PASSWORD = 'StrongPass123!'


class CaptureUploadTestCase(APITestCase):
    """Shared setup: an eligible student, today's event, and an
    already-opened (in-progress) evidence version ready to upload
    capture(s) against."""

    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.student = make_student('capturestudent', self.department)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)

        login = self.client.post(reverse('token-obtain-pair'), {
            'username': 'capturestudent', 'password': DEFAULT_PASSWORD,
        })
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {login.data["access"]}')

        open_response = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.assertEqual(open_response.status_code, status.HTTP_201_CREATED, open_response.data)
        self.evidence_id = open_response.data['id']
        self.version_id = open_response.data['versions'][0]['id']
        self.url = reverse('evidence-version-captures', args=[self.version_id])
        self.valid_timestamp = iso(noon_on(self.event.event_date))

    def _payload(self, **overrides):
        payload = {
            'capture_role': EvidenceCapture.Role.PRIMARY,
            'image': make_uploaded_image(),
            'device_capture_timestamp': self.valid_timestamp,
            'latitude': '12.971600',
            'longitude': '77.594600',
            'gps_accuracy': 15,
        }
        payload.update(overrides)
        return payload


class GpsValidationTests(CaptureUploadTestCase):
    def test_missing_latitude_rejected(self):
        payload = self._payload()
        del payload['latitude']
        response = self.client.post(self.url, payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_accuracy_rejected(self):
        payload = self._payload()
        del payload['gps_accuracy']
        response = self.client.post(self.url, payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_acceptable_accuracy_is_accepted(self):
        response = self.client.post(self.url, self._payload(gps_accuracy=20), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_excessive_accuracy_rejected(self):
        response = self.client.post(self.url, self._payload(gps_accuracy=500), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(EvidenceCapture.objects.filter(evidence_version_id=self.version_id).exists())

    def test_zero_accuracy_missing_is_not_treated_as_perfect(self):
        payload = self._payload()
        payload['gps_accuracy'] = ''
        response = self.client.post(self.url, payload, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_coordinates_rejected(self):
        response = self.client.post(self.url, self._payload(latitude='999', longitude='999'), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class VenueDistanceTests(CaptureUploadTestCase):
    def test_venue_distance_calculated_when_coordinates_configured(self):
        self.event.venue_latitude = 12.9716
        self.event.venue_longitude = 77.5946
        self.event.save(update_fields=['venue_latitude', 'venue_longitude'])

        response = self.client.post(
            self.url, self._payload(latitude='12.971600', longitude='77.594600'), format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNotNone(response.data['venue_distance'])
        self.assertLess(response.data['venue_distance'], 5)
        self.assertFalse(response.data['location_warning'])

    def test_venue_mismatch_sets_warning_but_does_not_reject(self):
        self.event.venue_latitude = 12.9716
        self.event.venue_longitude = 77.5946
        self.event.save(update_fields=['venue_latitude', 'venue_longitude'])

        response = self.client.post(
            self.url, self._payload(latitude='13.0827', longitude='80.2707'), format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertTrue(response.data['location_warning'])
        self.assertGreater(response.data['venue_distance'], 200)

    def test_no_venue_coordinates_means_no_distance_and_no_warning(self):
        response = self.client.post(self.url, self._payload(), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertIsNone(response.data['venue_distance'])
        self.assertFalse(response.data['location_warning'])


class TimestampValidationTests(CaptureUploadTestCase):
    def test_correct_event_date_timestamp_accepted(self):
        response = self.client.post(self.url, self._payload(), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_previous_day_timestamp_rejected(self):
        bad_timestamp = iso(noon_on(self.event.event_date) - timedelta(days=1))
        response = self.client.post(
            self.url, self._payload(device_capture_timestamp=bad_timestamp), format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_next_day_timestamp_rejected(self):
        bad_timestamp = iso(noon_on(self.event.event_date) + timedelta(days=1))
        response = self.client.post(
            self.url, self._payload(device_capture_timestamp=bad_timestamp), format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_far_future_timestamp_rejected(self):
        bad_timestamp = iso(timezone.now() + timedelta(days=2))
        response = self.client.post(
            self.url, self._payload(device_capture_timestamp=bad_timestamp), format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_server_received_timestamp_is_server_generated_not_client_supplied(self):
        spoofed = iso(timezone.now() - timedelta(days=365))
        response = self.client.post(
            self.url, {**self._payload(), 'server_received_timestamp': spoofed}, format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        capture = EvidenceCapture.objects.get(id=response.data['id'])
        self.assertGreater(capture.server_received_timestamp, timezone.now() - timedelta(minutes=5))


class ImageValidationTests(CaptureUploadTestCase):
    def test_invalid_content_rejected_even_with_image_mime_type(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        fake = SimpleUploadedFile('not-really-an-image.jpg', b'this is not an image', content_type='image/jpeg')
        response = self.client.post(self.url, self._payload(image=fake), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_oversized_file_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.test import override_settings

        oversized = SimpleUploadedFile('big.jpg', b'\xff' * (200 * 1024), content_type='image/jpeg')
        with override_settings(MAX_CAPTURE_FILE_SIZE=1024):
            response = self.client.post(self.url, self._payload(image=oversized), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_valid_image_accepted_and_hash_stored(self):
        import hashlib

        image = make_uploaded_image()
        data = image.read()
        image.seek(0)
        expected_hash = hashlib.sha256(data).hexdigest()

        response = self.client.post(self.url, self._payload(image=image), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data['sha256_hash'], expected_hash)
        self.assertEqual(response.data['mime_type'], 'image/jpeg')

    def test_unsafe_filename_does_not_affect_storage_path(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        data = make_uploaded_image().read()
        malicious = SimpleUploadedFile('../../../etc/passwd.jpg', data, content_type='image/jpeg')
        response = self.client.post(self.url, self._payload(image=malicious), format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        capture = EvidenceCapture.objects.get(id=response.data['id'])
        self.assertNotIn('..', capture.object_reference.name)
        self.assertNotIn('etc', capture.object_reference.name)
        self.assertNotIn('passwd', capture.object_reference.name)


class DuplicatePrimaryCaptureTests(CaptureUploadTestCase):
    def test_second_primary_capture_rejected(self):
        first = self.client.post(self.url, self._payload(), format='multipart')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)

        second = self.client.post(self.url, self._payload(), format='multipart')
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            EvidenceCapture.objects.filter(
                evidence_version_id=self.version_id, capture_role=EvidenceCapture.Role.PRIMARY,
            ).count(),
            1,
        )

    def test_additional_captures_are_unlimited(self):
        self.client.post(self.url, self._payload(), format='multipart')
        for _ in range(3):
            response = self.client.post(
                self.url, self._payload(capture_role=EvidenceCapture.Role.ADDITIONAL), format='multipart',
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

        self.assertEqual(
            EvidenceCapture.objects.filter(
                evidence_version_id=self.version_id, capture_role=EvidenceCapture.Role.ADDITIONAL,
            ).count(),
            3,
        )

    def test_cannot_upload_captures_after_submission(self):
        self.client.post(self.url, self._payload(), format='multipart')
        self.client.post(reverse('evidence-version-submit', args=[self.version_id]))

        response = self.client.post(
            self.url, self._payload(capture_role=EvidenceCapture.Role.ADDITIONAL), format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
