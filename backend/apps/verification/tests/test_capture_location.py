"""The capture's recorded location, end to end (requirements 13 and 18)."""

from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.participation.geocoding import Precision, ResolvedAddress
from apps.verification.models import EvidenceCapture

from .helpers import (
    make_college,
    make_department,
    make_event_coordinator,
    make_faculty,
    make_participation,
    make_student,
    make_submitted_evidence,
    make_todays_published_event,
    make_uploaded_image,
    noon_on,
)

BUILDING = ResolvedAddress(
    address='12, Example Road, Bengaluru, Karnataka, 560001, India',
    precision=Precision.EXACT,
    provider='nominatim',
)


class CaptureLocationTests(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.college = make_college()
        self.coordinator = make_event_coordinator('ec1', self.department)
        self.faculty = make_faculty('fac1', self.department)
        self.student = make_student('stu1', self.department)
        self.event = make_todays_published_event(
            created_by=self.coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)

    def _upload(self):
        self.client.force_authenticate(self.student)
        open_response = self.client.post(
            reverse('evidence-list'), {'participation': self.participation.id}, format='json',
        )
        self.assertIn(open_response.status_code, (status.HTTP_200_OK, status.HTTP_201_CREATED), open_response.data)
        version_id = open_response.data['versions'][0]['id']

        return self.client.post(
            reverse('evidence-version-captures', args=[version_id]),
            {
                'capture_role': 'PRIMARY',
                'image': make_uploaded_image(),
                'device_capture_timestamp': noon_on(self.event.event_date).isoformat(),
                'latitude': '12.970000',
                'longitude': '77.590000',
                'gps_accuracy': 8,
            },
            format='multipart',
        )

    @override_settings(GEOCODING_PROVIDER='nominatim')
    def test_a_resolved_address_is_stored_with_the_capture(self):
        with patch('apps.verification.services.reverse_geocode', return_value=BUILDING):
            response = self._upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        capture = EvidenceCapture.objects.get()
        self.assertEqual(capture.resolved_address, BUILDING.address)
        self.assertEqual(capture.address_precision, Precision.EXACT)
        self.assertIsNotNone(capture.address_resolved_at)

    @override_settings(GEOCODING_PROVIDER='nominatim')
    def test_the_capture_still_succeeds_when_geocoding_fails(self):
        # The photo, timestamp and coordinates are the evidence; an address is
        # an aid to reading them. A provider outage must never cost a student
        # the one day they are allowed to capture on.
        with patch('apps.verification.services.reverse_geocode', return_value=None):
            response = self._upload()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        capture = EvidenceCapture.objects.get()
        self.assertEqual(capture.resolved_address, '')
        self.assertEqual(capture.address_precision, Precision.UNRESOLVED)

    def test_coordinates_are_retained_alongside_the_address(self):
        with patch('apps.verification.services.reverse_geocode', return_value=BUILDING):
            self._upload()

        capture = EvidenceCapture.objects.get()
        # Requirement 13 keeps the underlying location information for
        # verification; the address never replaces it.
        self.assertEqual(str(capture.latitude), '12.970000')
        self.assertEqual(str(capture.longitude), '77.590000')
        self.assertEqual(capture.gps_accuracy, 8)


class LocationSummaryTests(APITestCase):
    """The single place that decides how a reviewer reads a location."""

    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.college = make_college()
        self.coordinator = make_event_coordinator('ec1', self.department)
        self.student = make_student('stu1', self.department)
        self.event = make_todays_published_event(
            created_by=self.coordinator, college=self.college, department=self.department,
        )
        participation = make_participation(student=self.student, event=self.event)
        _, self.version = make_submitted_evidence(participation=participation)
        self.capture = self.version.captures.get()

    def _summary(self, **fields):
        for key, value in fields.items():
            setattr(self.capture, key, value)
        return self.capture.location_summary

    def test_an_exact_address_is_stated_plainly(self):
        summary = self._summary(
            resolved_address='12, Example Road', address_precision=Precision.EXACT, gps_accuracy=8,
        )
        self.assertTrue(summary.startswith('12, Example Road'))
        self.assertIn('8 m', summary)

    def test_an_approximate_address_is_hedged(self):
        summary = self._summary(
            resolved_address='Example Road', address_precision=Precision.APPROXIMATE, gps_accuracy=120,
        )
        self.assertTrue(summary.startswith('Near '))

    def test_no_address_falls_back_to_coordinates_and_says_so(self):
        summary = self._summary(
            resolved_address='', address_precision=Precision.UNRESOLVED, gps_accuracy=15,
        )
        self.assertIn('address not resolved', summary)
        self.assertIn('15 m', summary)

    def test_faculty_see_the_location_on_the_evidence_record(self):
        self.capture.resolved_address = '12, Example Road'
        self.capture.address_precision = Precision.EXACT
        self.capture.save(update_fields=['resolved_address', 'address_precision'])

        faculty = make_faculty('fac1', self.department)
        self.client.force_authenticate(faculty)
        response = self.client.get(
            reverse('evidence-detail', args=[self.version.evidence_id]),
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        payload = str(response.data)
        self.assertIn('12, Example Road', payload)
        # And the coordinates are still there to be checked against it.
        self.assertIn('location_summary', payload)
