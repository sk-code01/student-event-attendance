"""
Analytics correctness against the deterministic fixture (§39).

Every assertion here is an exact number worked out by hand from
`helpers.build_world()`, not a smoke test. The awkward cases are deliberately
included: cancelled registrations, a cancelled event, rejected evidence, an
Event Coordinator override that flips an outcome, a rejected attendance, a pending OD, a
pending achievement, a department-less event, and empty datasets.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.verification.models import Evidence, EvidenceVerification

from .helpers import AuthMixin, build_world


class OverviewCorrectnessTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_world()

    def test_student_a_headline_numbers(self):
        self._auth_as('studenta')
        d = self.client.get(reverse('analytics-overview')).data
        self.assertEqual(d['registrations'], 3)       # 2 live + 1 cancelled
        self.assertEqual(d['live_registrations'], 2)
        self.assertEqual(d['participations'], 2)
        self.assertEqual(d['evidence_submitted'], 2)
        self.assertEqual(d['verified_participations'], 1)
        self.assertEqual(d['attendance_requests'], 1)
        self.assertEqual(d['attendance_approved'], 1)
        self.assertEqual(d['od_requests'], 1)
        self.assertEqual(d['od_approved'], 1)
        self.assertEqual(d['achievements'], 1)
        self.assertEqual(d['official_achievements'], 1)

    def test_participation_rate_uses_live_registrations_as_its_denominator(self):
        self._auth_as('studenta')
        d = self.client.get(reverse('analytics-overview')).data
        # 2 participations / 2 live registrations = 100%, not 2/3.
        self.assertEqual(d['participation_rate'], 100.0)
        self.assertIn('live', d['participation_rate_basis'])

    def test_a_cancelled_registration_is_excluded_from_the_rate_denominator(self):
        self._auth_as('studenta')
        d = self.client.get(reverse('analytics-overview')).data
        self.assertEqual(d['registrations'] - d['live_registrations'], 1)

    def test_student_c_has_a_registration_but_no_participation(self):
        self._auth_as('studentc')
        d = self.client.get(reverse('analytics-overview')).data
        self.assertEqual(d['registrations'], 1)
        self.assertEqual(d['participations'], 0)
        self.assertEqual(d['participation_rate'], 0.0)

    def test_a_rate_with_a_zero_denominator_is_null_not_zero(self):
        """"Nothing was requested" and "everything was refused" are different
        facts; reporting both as 0% would invent data."""
        self._auth_as('studentc')
        d = self.client.get(reverse('analytics-attendance')).data
        self.assertEqual(d['total_requests'], 0)
        self.assertIsNone(d['approval_rate'])


class EffectiveVerificationTests(AuthMixin, APITestCase):
    """§12: an overridden Faculty decision must never be counted as the final
    result."""

    def setUp(self):
        self.w = build_world()

    def test_event_coordinator_override_flips_the_effective_outcome(self):
        # student_b's evidence: Faculty VERIFIED, Event Coordinator overrode to REJECTED.
        self._auth_as('studentb')
        d = self.client.get(reverse('analytics-verification')).data
        self.assertEqual(d['total_evidence'], 1)
        self.assertEqual(d['verified'], 0, 'the superseded Faculty VERIFIED was counted')
        self.assertEqual(d['rejected'], 1)
        self.assertEqual(d['event_coordinator_overrides'], 1)

    def test_the_faculty_decision_row_still_exists_underneath(self):
        """The override changes the effective outcome without erasing history,
        so the Faculty VERIFIED row is still on record."""
        faculty_rows = EvidenceVerification.objects.filter(
            evidence_version__evidence=self.w.ev_b1, is_event_coordinator_override=False,
        )
        self.assertEqual(faculty_rows.count(), 1)
        self.assertEqual(faculty_rows.first().decision, EvidenceVerification.Decision.VERIFIED)
        self.assertEqual(Evidence.objects.get(pk=self.w.ev_b1.pk).status,
                         Evidence.Status.REJECTED)

    def test_department_verification_counts_use_effective_decisions(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-verification')).data
        # CS evidence: a1 VERIFIED, a2 REJECTED, b1 REJECTED-by-override.
        self.assertEqual(d['total_evidence'], 3)
        self.assertEqual(d['verified'], 1)
        self.assertEqual(d['rejected'], 2)
        self.assertEqual(d['event_coordinator_overrides'], 1)
        self.assertEqual(d['verification_rate'], round(1 * 100 / 3, 2))
        self.assertIn('effective decision', d['decision_basis'])


class WorkflowAnalyticsTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_world()

    def test_attendance_counts_and_rate(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-attendance')).data
        self.assertEqual(d['total_requests'], 2)
        self.assertEqual(d['approved'], 1)
        self.assertEqual(d['rejected'], 1)
        self.assertEqual(d['pending'], 0)
        self.assertEqual(d['approval_rate'], 50.0)

    def test_od_counts_are_independent_of_attendance(self):
        self._auth_as('hodcs')
        attendance = self.client.get(reverse('analytics-attendance')).data
        od = self.client.get(reverse('analytics-od')).data
        # student_b: attendance REJECTED but OD still PENDING — the two
        # workflows must not have been conflated.
        self.assertEqual(attendance['rejected'], 1)
        self.assertEqual(od['pending'], 1)
        self.assertEqual(od['approved'], 1)
        self.assertEqual(od['rejected'], 0)

    def test_od_approval_rate_excludes_pending_from_its_denominator(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-od')).data
        # 1 approved of 1 decided (the pending one is not counted).
        self.assertEqual(d['approval_rate'], 100.0)
        self.assertIn('pending excluded', d['approval_rate_basis'])

    def test_only_approved_achievements_are_official(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-achievements')).data
        self.assertEqual(d['total_achievements'], 2)
        self.assertEqual(d['official_achievements'], 1)
        self.assertEqual(d['pending_approval'], 1)

    def test_registration_cancellation_rate(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-registrations')).data
        # CS scope: student_a 2 (cs_event + cs_cancelled), student_b 1,
        # student_c 1 — the cancelled one is against the orphan event, which
        # is outside the CS department.
        self.assertEqual(d['total_registrations'], 4)
        self.assertEqual(d['cancelled_registrations'], 0)
        self.assertEqual(d['cancellation_rate'], 0.0)

    def test_event_lifecycle_counts_read_the_persisted_status(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-events')).data
        self.assertEqual(d['total_events'], 2)
        self.assertEqual(d['cancelled_events'], 1)
        self.assertEqual(d['published_events'], 1)

    def test_participation_breakdowns_are_present_and_scoped(self):
        self._auth_as('hodcs')
        d = self.client.get(reverse('analytics-participation')).data
        titles = {row['event_title'] for row in d['by_event']}
        self.assertIn('CS Event', titles)
        self.assertNotIn('EC Event', titles)
        self.assertNotIn('Orphan Event', titles)


class DepartmentAnalyticsTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_world()

    def test_admin_sees_both_departments_with_correct_totals(self):
        self._auth_as('sysadmin')
        rows = {r['department']: r for r in self.client.get(reverse('analytics-departments')).data['departments']}
        self.assertEqual(rows['Computer Science']['participations'], 3)
        self.assertEqual(rows['Electronics']['participations'], 1)
        self.assertEqual(rows['Computer Science']['attendance_approved'], 1)
        self.assertEqual(rows['Electronics']['attendance_approved'], 1)

    def test_department_less_events_are_reported_separately_not_attributed(self):
        self._auth_as('sysadmin')
        d = self.client.get(reverse('analytics-departments')).data
        self.assertEqual(d['department_less_events'], 1)
        for row in d['departments']:
            self.assertIsNotNone(row['department'])

    def test_a_department_with_events_but_no_participations_still_appears(self):
        from apps.analytics.tests.helpers import make_department, make_event_coordinator, make_todays_published_event
        empty_dept = make_department('ME', 'Mechanical')
        event_coordinator = make_event_coordinator('hodme', empty_dept)
        make_todays_published_event(
            created_by=event_coordinator, college=self.w.college, department=empty_dept, title='ME Event',
        )
        self._auth_as('sysadmin')
        rows = {r['department']: r for r in self.client.get(reverse('analytics-departments')).data['departments']}
        self.assertIn('Mechanical', rows)
        self.assertEqual(rows['Mechanical']['participations'], 0)
        self.assertEqual(rows['Mechanical']['events'], 1)


class EmptyDataTests(AuthMixin, APITestCase):
    """A role with no data must get zeros and empty lists, never an error."""

    def setUp(self):
        self.w = build_world()

    def test_student_with_nothing_gets_zeros_across_every_endpoint(self):
        from apps.analytics.tests.helpers import make_student
        make_student('lonelystudent', self.w.cs)
        self._auth_as('lonelystudent')

        for name in ('analytics-overview', 'analytics-participation', 'analytics-events',
                     'analytics-registrations', 'analytics-attendance', 'analytics-od',
                     'analytics-achievements', 'analytics-verification'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, status.HTTP_200_OK, name)
            for key, value in response.data.items():
                if isinstance(value, int):
                    self.assertEqual(value, 0, f'{name}.{key} should be 0')
                if isinstance(value, list):
                    self.assertEqual(value, [], f'{name}.{key} should be empty')

    def test_trends_for_an_empty_scope_returns_an_empty_series(self):
        from apps.analytics.tests.helpers import make_student
        make_student('lonelystudent', self.w.cs)
        self._auth_as('lonelystudent')
        d = self.client.get(reverse('analytics-trends')).data
        self.assertEqual(d['series'], [])
        self.assertEqual(d['statistics']['registrations']['direction'], 'insufficient_data')

    def test_a_date_range_matching_nothing_returns_zeros(self):
        self._auth_as('hodcs')
        d = self.client.get(
            reverse('analytics-overview'), {'date_from': '2000-01-01', 'date_to': '2000-01-31'},
        ).data
        self.assertEqual(d['registrations'], 0)
        self.assertEqual(d['participations'], 0)
        self.assertIsNone(d['participation_rate'])
