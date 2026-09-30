"""
Phase 9 §8 — user-controlled filters and ids never reach the ORM raw, never
500, and never behave as SQL. There is no raw SQL in the application (the
only `cursor.execute` is the health check's constant `SELECT 1`), so the
checks here are behavioural: hostile values are either rejected with 400 or
treated as inert literals.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.audit.models import AuditLog

from .helpers import AuthMixin, build_universe

INJECTION = ["'", '"', ';', '--', '/*', "' OR 1=1 --", "1; DROP TABLE accounts_user; --",
             "%27%20OR%201%3D1", "\\", "\x00", "🙂"]


class FilterInjectionTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()
        AuditLog.record(actor=self.u.admin, action='EVENT_CREATED', description="literal ' OR 1=1 -- text")

    def test_text_filters_treat_payloads_as_inert_literals(self):
        self._auth_as('sysadmin')
        total = self.client.get(reverse('auditlog-list')).data['count']
        for payload in INJECTION:
            for name, param in (('auditlog-list', 'search'), ('auditlog-list', 'action'),
                                ('activity-list', 'search'), ('analytics-overview', 'category'),
                                ('registration-request-list', 'status'), ('report-preview', 'category')):
                url = reverse(name, args=['event']) if name == 'report-preview' else reverse(name)
                response = self.client.get(url, {param: payload})
                self.assertIn(response.status_code, (200, 400), f'{name}?{param}={payload!r} -> {response.status_code}')
                if name == 'auditlog-list' and param == 'search' and response.status_code == 200:
                    self.assertLessEqual(response.data['count'], total)
        # The table is intact and the literal row is still findable.
        self.assertEqual(self.client.get(reverse('auditlog-list'), {'search': "' OR 1=1 --"}).data['count'], 1)

    def test_numeric_filters_reject_non_numbers_with_400_not_500(self):
        self._auth_as('sysadmin')
        cases = [
            (reverse('registration-list'), {'event': 'abc'}),
            (reverse('registration-list'), {'event': "1 OR 1=1"}),
            (reverse('auditlog-list'), {'actor': 'abc'}),
            (reverse('auditlog-list'), {'date_from': 'not-a-date'}),
            (reverse('auditlog-list'), {'date_to': '2026-13-45'}),
            (reverse('activity-list'), {'date_from': "'"}),
            (reverse('analytics-overview'), {'event': 'abc'}),
            (reverse('analytics-overview'), {'department': "1'"}),
            (reverse('analytics-overview'), {'student': '-1'}),
            (reverse('analytics-overview'), {'date_from': 'garbage'}),
            (reverse('analytics-trends'), {'period': 'hourly'}),
            (reverse('ai-anomalies'), {'evidence': 'abc'}),
            (reverse('ai-anomalies'), {'limit': 'abc'}),
            (reverse('report-export', args=['event']), {'file_format': '../../etc/passwd'}),
            (reverse('auditlog-list'), {'search': 'a\x00b'}),
            (reverse('analytics-overview'), {'category': 'a\x00b'}),
        ]
        for url, params in cases:
            response = self.client.get(url, params)
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST,
                             f'{url} {params} -> {response.status_code}')

    def test_student_eligibility_rejects_bad_event_ids_with_400(self):
        self._auth_as('studenta')
        for value in ('abc', '', '1e9', '99999999'):
            response = self.client.get(reverse('participation-eligibility'), {'event': value})
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, value)

    def test_pagination_parameters_are_hardened(self):
        self._auth_as('sysadmin')
        for value in ('abc', '0', '-1', '999999', "1'"):
            response = self.client.get(reverse('auditlog-list'), {'page': value})
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, value)
        # page_size is not a supported override: it is ignored, never honoured.
        response = self.client.get(reverse('auditlog-list'), {'page_size': 100000})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertLessEqual(len(response.data['results']), 20)

    def test_unknown_report_type_and_traversal_in_the_path_are_404(self):
        self._auth_as('sysadmin')
        for report_type in ('not-a-report', '..', '%2e%2e', 'event%2500'):
            response = self.client.get(f'/api/v1/reports/{report_type}/export/?file_format=csv')
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, report_type)
        # A NUL byte anywhere in the URL is refused before routing.
        response = self.client.get('/api/v1/reports/event%00/export/?file_format=csv')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # The allowlist is case-insensitive on purpose; the key is normalised, never used as a path.
        self.assertEqual(self.client.get('/api/v1/reports/SYSTEM/export/?file_format=csv').status_code, 200)

    def test_oversized_and_binary_junk_bodies_are_400_not_500(self):
        self._auth_as('hoda')
        response = self.client.post(reverse('event-list'), 'not json at all', content_type='application/json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        huge = {'title': 'x' * 10000, 'venue': 'v', 'category': 'c', 'event_date': '2030-01-01',
                'conducting_college': 1, 'registration_start_date': '2029-01-01',
                'registration_end_date': '2029-12-31'}
        response = self.client.post(reverse('event-list'), huge)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self._auth_as('studenta')
        response = self.client.post(reverse('registration-list'), {'event': [1, 2, 3]})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(reverse('registration-list'), {'event': {'id': 1}}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(reverse('registration-list'), {'event': 'a\x00b'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
