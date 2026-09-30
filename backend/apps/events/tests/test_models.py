from datetime import timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone

from apps.events.models import Event

from .helpers import make_college, make_department, make_event, make_event_coordinator


class EventDateConstraintTests(TestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)

    def test_registration_end_must_be_before_event_date(self):
        today = timezone.localdate()
        with self.assertRaises(IntegrityError):
            Event.objects.create(
                title='Bad Event', venue='Hall', category='Technical',
                conducting_college=self.college, created_by=self.event_coordinator,
                event_date=today + timedelta(days=5),
                registration_start_date=today,
                registration_end_date=today + timedelta(days=5),  # equal, not before -> violates
            )

    def test_registration_start_must_be_on_or_before_end(self):
        today = timezone.localdate()
        with self.assertRaises(IntegrityError):
            Event.objects.create(
                title='Bad Event', venue='Hall', category='Technical',
                conducting_college=self.college, created_by=self.event_coordinator,
                event_date=today + timedelta(days=10),
                registration_start_date=today + timedelta(days=5),
                registration_end_date=today + timedelta(days=1),
            )

    def test_valid_date_relationship_is_accepted(self):
        event = make_event(created_by=self.event_coordinator, college=self.college)
        self.assertIsNotNone(event.id)


class IsRegistrationOpenTests(TestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)

    def test_open_when_published_and_within_window(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, status=Event.Status.PUBLISHED)
        self.assertTrue(event.is_registration_open())

    def test_closed_when_draft(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, status=Event.Status.DRAFT)
        self.assertFalse(event.is_registration_open())

    def test_closed_before_window_starts(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, status=Event.Status.PUBLISHED,
            registration_starts_in=2, registration_ends_in=5,
        )
        self.assertFalse(event.is_registration_open())

    def test_closed_after_window_ends(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, status=Event.Status.PUBLISHED,
            days_until_event=10, registration_starts_in=-5, registration_ends_in=-1,
        )
        self.assertFalse(event.is_registration_open())


class MarkPastEventsCompletedTests(TestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)

    def test_published_past_event_is_marked_completed(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, status=Event.Status.PUBLISHED,
            days_until_event=-1, registration_starts_in=-10, registration_ends_in=-2,
        )
        Event.objects.mark_past_events_completed()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.COMPLETED)

    def test_future_published_event_is_untouched(self):
        event = make_event(created_by=self.event_coordinator, college=self.college, status=Event.Status.PUBLISHED)
        Event.objects.mark_past_events_completed()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.PUBLISHED)

    def test_draft_past_event_is_not_auto_completed(self):
        event = make_event(
            created_by=self.event_coordinator, college=self.college, status=Event.Status.DRAFT,
            days_until_event=-1, registration_starts_in=-10, registration_ends_in=-2,
        )
        Event.objects.mark_past_events_completed()
        event.refresh_from_db()
        self.assertEqual(event.status, Event.Status.DRAFT)
