"""
Phase 9 §11 — the event-date rule at the institution-timezone boundary, and
the server-owned timestamps.
"""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.test import APITestCase

from apps.participation.validation import validate_device_timestamp_for_event
from apps.verification.tests.helpers import iso, make_uploaded_image

from .helpers import AuthMixin, build_universe, make_participation

IST = ZoneInfo('Asia/Kolkata')


class EventDateBoundaryTests(SimpleTestCase):
    """Pure validation, aware datetimes only. `event_date` is yesterday so no
    future-skew rule interferes with the calendar rule under test."""

    def setUp(self):
        self.assertEqual(settings.TIME_ZONE, 'Asia/Kolkata')
        self.event_date = timezone.localdate() - timedelta(days=1)

    def _at(self, day, hh, mm, ss, tz=IST):
        return datetime.combine(day, time(hh, mm, ss), tzinfo=tz)

    def test_first_and_last_second_of_the_event_day_in_ist_are_accepted(self):
        validate_device_timestamp_for_event(self._at(self.event_date, 0, 0, 0), self.event_date)
        validate_device_timestamp_for_event(self._at(self.event_date, 23, 59, 59), self.event_date)

    def test_one_second_past_midnight_ist_is_the_next_day(self):
        with self.assertRaises(serializers.ValidationError):
            validate_device_timestamp_for_event(self._at(self.event_date + timedelta(days=1), 0, 0, 1), self.event_date)

    def test_the_utc_instant_is_judged_in_ist_not_utc(self):
        # 20:00 UTC on the event date is 01:30 IST the NEXT day -> rejected.
        late_utc = self._at(self.event_date, 20, 0, 0, tz=ZoneInfo('UTC'))
        with self.assertRaises(serializers.ValidationError):
            validate_device_timestamp_for_event(late_utc, self.event_date)
        # 18:29:59 UTC is 23:59:59 IST the same day -> accepted.
        validate_device_timestamp_for_event(self._at(self.event_date, 18, 29, 59, tz=ZoneInfo('UTC')), self.event_date)
        # 18:30:00 UTC the day BEFORE is 00:00:00 IST on the event date -> accepted.
        validate_device_timestamp_for_event(
            self._at(self.event_date - timedelta(days=1), 18, 30, 0, tz=ZoneInfo('UTC')), self.event_date,
        )

    def test_future_timestamps_beyond_clock_skew_are_rejected_even_on_the_right_day(self):
        today = timezone.localdate()
        with self.assertRaises(serializers.ValidationError):
            validate_device_timestamp_for_event(timezone.now() + timedelta(minutes=6), today)
        # Inside the 5-minute skew allowance, and today: accepted.
        validate_device_timestamp_for_event(timezone.now() + timedelta(minutes=4), today)

    def test_missing_timestamp_is_rejected(self):
        with self.assertRaises(serializers.ValidationError):
            validate_device_timestamp_for_event(None, self.event_date)


class ServerOwnedTimestampTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()
        # make_participation creates the registration itself.
        self.participation = make_participation(student=self.u.a.other_student, event=self.u.a.event)
        self._auth_as('studenta2')
        opened = self.client.post(reverse('evidence-list'), {'participation': self.participation.id})
        self.version_id = opened.data['versions'][0]['id']

    def _upload(self, **overrides):
        payload = {
            'capture_role': 'PRIMARY', 'image': make_uploaded_image(),
            'device_capture_timestamp': iso(timezone.now() - timedelta(seconds=5)),
            'latitude': '12.971600', 'longitude': '77.594600', 'gps_accuracy': 15,
        }
        payload.update(overrides)
        url = reverse('evidence-version-captures', args=[self.version_id])
        return self.client.post(url, payload, format='multipart')

    def test_server_received_created_and_submitted_timestamps_cannot_be_supplied(self):
        before = timezone.now()
        response = self._upload(server_received_timestamp='2001-01-01T00:00:00Z', created_at='2001-01-01T00:00:00Z')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        received = datetime.fromisoformat(response.data['server_received_timestamp'].replace('Z', '+00:00'))
        self.assertGreaterEqual(received, before - timedelta(seconds=5))
        submit = self.client.post(reverse('evidence-version-submit', args=[self.version_id]),
                                  {'submitted_at': '2001-01-01T00:00:00Z'})
        self.assertEqual(submit.status_code, status.HTTP_200_OK, submit.data)
        submitted = datetime.fromisoformat(submit.data['submitted_at'].replace('Z', '+00:00'))
        self.assertGreaterEqual(submitted, before - timedelta(seconds=5))

    def test_naive_and_garbage_device_timestamps_are_rejected(self):
        for value in ('2001-01-01 12:00:00', 'yesterday', '', '0', '2026-13-40T00:00:00Z'):
            response = self._upload(device_capture_timestamp=value)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, value)

    def test_wrong_day_capture_is_rejected_regardless_of_upload_time(self):
        yesterday_noon = datetime.combine(timezone.localdate() - timedelta(days=1), time(12, 0), tzinfo=IST)
        response = self._upload(device_capture_timestamp=iso(yesterday_noon))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('event date', str(response.data))
