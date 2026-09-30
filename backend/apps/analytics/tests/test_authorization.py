"""
The analytics authorization matrix (§36) and filter-manipulation/IDOR
surface (§37).

These are the tests that matter most in Phase 7: everything else is arithmetic,
but a mistake here leaks another student's or another department's data. Each
one attempts the manipulation a real attacker would try — passing someone
else's id — rather than trusting that a frontend guard exists.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import AuthMixin, build_world

ENDPOINTS = [
    'analytics-overview', 'analytics-participation', 'analytics-events',
    'analytics-registrations', 'analytics-attendance', 'analytics-od',
    'analytics-achievements', 'analytics-verification', 'analytics-trends',
]


class AnalyticsAccessTests(AuthMixin, APITestCase):
    def setUp(self):
        self.w = build_world()

    # --- authentication ----------------------------------------------------

    def test_every_endpoint_requires_authentication(self):
        self.client.credentials()
        for name in ENDPOINTS + ['analytics-departments']:
            self.assertEqual(
                self.client.get(reverse(name)).status_code,
                status.HTTP_401_UNAUTHORIZED,
                f'{name} allowed an anonymous request',
            )

    def test_every_role_can_reach_its_own_analytics(self):
        for username in ('studenta', 'facultycs', 'hodcs', 'sysadmin'):
            self._auth_as(username)
            for name in ENDPOINTS:
                self.assertEqual(
                    self.client.get(reverse(name)).status_code, status.HTTP_200_OK,
                    f'{username} could not reach {name}',
                )

    # --- student scope -----------------------------------------------------

    def test_student_sees_only_their_own_numbers(self):
        self._auth_as('studenta')
        a = self.client.get(reverse('analytics-overview')).data
        self._auth_as('studentb')
        b = self.client.get(reverse('analytics-overview')).data

        self.assertEqual(a['participations'], 2)
        self.assertEqual(b['participations'], 1)
        self.assertNotEqual(a['registrations'], b['registrations'])

    def test_student_cannot_request_another_students_analytics(self):
        self._auth_as('studenta')
        response = self.client.get(
            reverse('analytics-overview'), {'student': self.w.student_b.id},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_passing_their_own_id_is_accepted(self):
        self._auth_as('studenta')
        response = self.client.get(
            reverse('analytics-overview'), {'student': self.w.student_a.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['participations'], 2)

    def test_student_cannot_filter_by_department(self):
        self._auth_as('studenta')
        response = self.client.get(
            reverse('analytics-overview'), {'department': self.w.cs.id},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_student_cannot_request_department_analytics_at_all(self):
        self._auth_as('studenta')
        self.assertEqual(
            self.client.get(reverse('analytics-departments')).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_student_cannot_filter_by_an_event_they_never_registered_for(self):
        self._auth_as('studentc')
        response = self.client.get(
            reverse('analytics-overview'), {'event': self.w.ec_event.id},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- faculty scope -----------------------------------------------------

    def test_faculty_is_department_scoped(self):
        self._auth_as('facultycs')
        cs = self.client.get(reverse('analytics-overview')).data
        self._auth_as('facultyec')
        ec = self.client.get(reverse('analytics-overview')).data

        self.assertEqual(cs['participations'], 3)
        self.assertEqual(ec['participations'], 1)

    def test_faculty_cannot_name_another_department(self):
        self._auth_as('facultycs')
        response = self.client.get(
            reverse('analytics-overview'), {'department': self.w.ec.id},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_cannot_reach_department_comparison(self):
        self._auth_as('facultycs')
        self.assertEqual(
            self.client.get(reverse('analytics-departments')).status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_faculty_cannot_filter_by_another_departments_event(self):
        self._auth_as('facultycs')
        response = self.client.get(
            reverse('analytics-overview'), {'event': self.w.ec_event.id},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_faculty_cannot_name_a_student_outside_their_department(self):
        self._auth_as('facultycs')
        response = self.client.get(
            reverse('analytics-overview'), {'student': self.w.student_ec.id},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_may_narrow_to_a_student_inside_their_department(self):
        self._auth_as('facultycs')
        response = self.client.get(
            reverse('analytics-overview'), {'student': self.w.student_a.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['participations'], 2)

    # --- event_coordinator scope ---------------------------------------------------------

    def test_event_coordinator_is_department_scoped(self):
        self._auth_as('hodcs')
        self.assertEqual(self.client.get(reverse('analytics-overview')).data['participations'], 3)
        self._auth_as('hodec')
        self.assertEqual(self.client.get(reverse('analytics-overview')).data['participations'], 1)

    def test_event_coordinator_cannot_request_another_department(self):
        self._auth_as('hodcs')
        response = self.client.get(
            reverse('analytics-departments'), {'department': self.w.ec.id},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_coordinator_department_comparison_contains_only_their_department(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('analytics-departments'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = {row['department'] for row in response.data['departments']}
        self.assertEqual(names, {'Computer Science'})
        self.assertNotIn('Electronics', names)

    def test_event_coordinator_naming_their_own_department_is_a_harmless_narrowing(self):
        self._auth_as('hodcs')
        response = self.client.get(
            reverse('analytics-departments'), {'department': self.w.cs.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # --- admin scope -------------------------------------------------------

    def test_admin_sees_system_wide_totals(self):
        self._auth_as('sysadmin')
        data = self.client.get(reverse('analytics-overview')).data
        self.assertEqual(data['participations'], 4)  # 3 CS + 1 EC

    def test_admin_may_narrow_to_any_department(self):
        self._auth_as('sysadmin')
        response = self.client.get(
            reverse('analytics-overview'), {'department': self.w.ec.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['participations'], 1)

    def test_admin_department_comparison_lists_every_department(self):
        self._auth_as('sysadmin')
        names = {row['department'] for row in self.client.get(reverse('analytics-departments')).data['departments']}
        self.assertEqual(names, {'Computer Science', 'Electronics'})

    # --- filter validation -------------------------------------------------

    def test_malformed_dates_are_rejected(self):
        self._auth_as('hodcs')
        for params in ({'date_from': 'yesterday'}, {'date_to': '15-09-2026'}, {'date_from': '2026-13-01'}):
            self.assertEqual(
                self.client.get(reverse('analytics-overview'), params).status_code,
                status.HTTP_400_BAD_REQUEST,
                params,
            )

    def test_inverted_date_range_is_rejected(self):
        self._auth_as('hodcs')
        response = self.client.get(
            reverse('analytics-overview'), {'date_from': '2026-09-30', 'date_to': '2026-09-01'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unsupported_period_is_rejected(self):
        self._auth_as('hodcs')
        response = self.client.get(reverse('analytics-trends'), {'period': 'hourly'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_numeric_ids_are_rejected(self):
        self._auth_as('hodcs')
        for params in ({'event': 'abc'}, {'department': 'x'}, {'student': 'y'}):
            self.assertEqual(
                self.client.get(reverse('analytics-overview'), params).status_code,
                status.HTTP_400_BAD_REQUEST,
                params,
            )

    def test_unknown_ids_resolve_to_404(self):
        self._auth_as('sysadmin')
        for params in ({'event': 999999}, {'department': 999999}, {'student': 999999}):
            self.assertEqual(
                self.client.get(reverse('analytics-overview'), params).status_code,
                status.HTTP_404_NOT_FOUND,
                params,
            )

    def test_unknown_query_parameters_are_ignored_not_honoured(self):
        """An unrecognised parameter must not silently widen scope."""
        self._auth_as('studenta')
        baseline = self.client.get(reverse('analytics-overview')).data
        response = self.client.get(
            reverse('analytics-overview'),
            {'all': 'true', 'scope': 'system', 'user_id': self.w.student_b.id},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['participations'], baseline['participations'])
