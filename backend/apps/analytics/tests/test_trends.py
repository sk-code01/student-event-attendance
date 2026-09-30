"""
Trend analytics (§40) and the statistical helpers (§19).

Records are created across explicit dates so grouping, boundaries and
period-over-period arithmetic can be asserted exactly. All three periods are
implemented, so all three are tested.

These are statistics, not ML — the assertions below are arithmetic on counts.
"""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.analytics.trends import moving_average, summarise
from apps.registrations.models import Registration

from .helpers import AuthMixin, build_world


class TrendGroupingTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_world()
        # Three registrations placed on known days: two in one month, one in
        # the month before, so monthly grouping has two distinct buckets.
        now = timezone.localtime()
        self.recent = now.replace(hour=12, minute=0, second=0, microsecond=0)
        self.older = self.recent - timedelta(days=45)

        from apps.analytics.tests.helpers import make_student
        student = make_student('trendstudent', self.w.cs)
        for when in (self.recent, self.recent - timedelta(days=1), self.older):
            registration = Registration.objects.create(student=student, event=self.w.cs_event) \
                if not Registration.objects.filter(student=student, event=self.w.cs_event).exists() else None
            if registration is None:
                # One registration per (student, event) is enforced by the DB,
                # so extra points use extra events.
                from apps.analytics.tests.helpers import make_todays_published_event
                event = make_todays_published_event(
                    created_by=self.w.event_coordinator_cs, college=self.w.college, department=self.w.cs,
                    title=f'Trend Event {when.date()}',
                )
                registration = Registration.objects.create(student=student, event=event)
            Registration.objects.filter(pk=registration.pk).update(registered_at=when)

    def test_monthly_grouping_produces_a_bucket_per_month(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-trends'), {'period': 'monthly'}).data
        self.assertEqual(d['period'], 'monthly')
        labels = [row['period'] for row in d['series']]
        self.assertIn(self.recent.strftime('%Y-%m'), labels)
        self.assertIn(self.older.strftime('%Y-%m'), labels)
        self.assertEqual(sorted(labels), labels, 'series must be chronological')

    def test_daily_grouping_produces_a_bucket_per_day(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-trends'), {'period': 'daily'}).data
        labels = [row['period'] for row in d['series']]
        self.assertIn(self.recent.strftime('%Y-%m-%d'), labels)
        self.assertTrue(all(len(label) == 10 for label in labels), labels)

    def test_weekly_grouping_is_accepted_and_labelled(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-trends'), {'period': 'weekly'}).data
        self.assertEqual(d['period'], 'weekly')
        self.assertTrue(all('-W' in row['period'] for row in d['series']), d['series'])

    def test_the_series_reports_the_configured_application_timezone(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-trends')).data
        self.assertEqual(d['timezone'], str(timezone.get_current_timezone()))

    def test_date_boundaries_are_inclusive(self):
        self._auth_as('hodcs')
        day = self.recent.date().isoformat()
        d = self.client.get(
            reverse('analytics-trends'), {'period': 'daily', 'date_from': day, 'date_to': day},
        ).data
        labels = [row['period'] for row in d['series']]
        self.assertEqual(labels, [day])

    def test_a_range_before_all_data_returns_an_empty_series(self):
        self._auth_as('hodcs')
        d = self.client.get(
            reverse('analytics-trends'), {'date_from': '2000-01-01', 'date_to': '2000-12-31'},
        ).data
        self.assertEqual(d['series'], [])

    def test_trends_are_scoped_like_every_other_endpoint(self):
        self._auth_as('facultyec')
        ec = self.client.get(reverse('analytics-trends')).data
        total = sum(row['participations'] for row in ec['series'])
        self.assertEqual(total, 1, 'EC faculty saw participations outside their department')


class StatisticsTests(APITestCase):
    """Unit tests for the plain-arithmetic helpers."""

    def test_direction_rises_falls_and_holds_steady(self):
        self.assertEqual(summarise([1, 5])['direction'], 'rising')
        self.assertEqual(summarise([5, 1])['direction'], 'falling')
        self.assertEqual(summarise([3, 3])['direction'], 'steady')

    def test_a_single_period_is_insufficient_for_a_direction(self):
        stats = summarise([7])
        self.assertEqual(stats['direction'], 'insufficient_data')
        self.assertIsNone(stats['change'])
        self.assertIsNone(stats['previous'])

    def test_an_empty_series_is_handled_without_dividing_by_zero(self):
        stats = summarise([])
        self.assertEqual(stats['total'], 0)
        self.assertEqual(stats['periods'], 0)
        self.assertIsNone(stats['average'])
        self.assertEqual(stats['direction'], 'insufficient_data')

    def test_percentage_change_is_none_when_the_previous_period_was_zero(self):
        """Growth from zero has no meaningful percentage; reporting 100% or
        infinity would be inventing a number."""
        stats = summarise([0, 5])
        self.assertEqual(stats['change'], 5)
        self.assertIsNone(stats['change_percent'])
        self.assertEqual(stats['direction'], 'rising')

    def test_percentage_change_arithmetic(self):
        stats = summarise([4, 5])
        self.assertEqual(stats['change'], 1)
        self.assertEqual(stats['change_percent'], 25.0)

    def test_average_and_total(self):
        stats = summarise([1, 2, 3, 4])
        self.assertEqual(stats['total'], 10)
        self.assertEqual(stats['average'], 2.5)
        self.assertEqual(stats['latest'], 4)
        self.assertEqual(stats['previous'], 3)

    def test_moving_average_window(self):
        self.assertEqual(moving_average([1, 2, 3, 4, 5], window=3), [2.0, 3.0, 4.0])

    def test_moving_average_is_empty_when_there_is_less_data_than_the_window(self):
        """Padding with partial averages would read as real data points."""
        self.assertEqual(moving_average([1, 2], window=3), [])
