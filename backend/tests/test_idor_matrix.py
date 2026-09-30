"""
Phase 9 §6 — the IDOR matrix across every resource type.

Convention under test (PROJECT_HANDOFF §11): an object outside the caller's
visible queryset is 404; a visible object with a forbidden action is 403.
The two exceptions the codebase deliberately makes (registration-request
review by another department's Event Coordinator, and the bare draft-event pk check on
registration) are pinned as they are, so a future change is a conscious one.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .helpers import AuthMixin, build_universe


class CrossStudentIdorTests(AuthMixin, APITestCase):
    """Student A2 (same department) and Student B (other department) against
    Student A's records."""

    def setUp(self):
        self.u = build_universe()

    def _detail_urls(self):
        a = self.u.a
        return [
            reverse('registration-detail', args=[a.registration.id]),
            reverse('participation-detail', args=[a.participation.id]),
            reverse('evidence-detail', args=[a.evidence.id]),
            reverse('evidence-capture-image', args=[a.capture.id]),
            reverse('attendance-detail', args=[a.attendance.id]),
            reverse('od-request-detail', args=[a.od.id]),
            reverse('achievement-detail', args=[a.achievement.id]),
            reverse('notification-detail', args=[a.notification.id]),
        ]

    def test_other_students_get_404_on_every_detail(self):
        for username in ('studenta2', 'studentb'):
            self._auth_as(username)
            for url in self._detail_urls():
                self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND, f'{username} {url}')

    def test_other_students_cannot_mutate_anything_of_student_a(self):
        a = self.u.a
        for username in ('studenta2', 'studentb'):
            self._auth_as(username)
            attempts = [
                ('post', reverse('registration-cancel', args=[a.registration.id]), {}),
                ('post', reverse('notification-read', args=[a.notification.id]), {}),
                ('post', reverse('evidence-version-captures', args=[a.version.id]), {}),
                ('post', reverse('evidence-version-submit', args=[a.version.id]), {}),
                ('post', reverse('evidence-list'), {'participation': a.participation.id}),
                ('post', reverse('participation-list'), {'event': a.event.id}),  # not registered -> 400
            ]
            for method, url, body in attempts:
                response = getattr(self.client, method)(url, body)
                self.assertIn(response.status_code, (400, 403, 404), f'{username} {method} {url}')
                self.assertNotEqual(response.status_code, 200, f'{username} {method} {url}')

    def test_student_cannot_perform_any_staff_decision(self):
        a = self.u.a
        self._auth_as('studenta')
        for url in (
            reverse('evidence-verify', args=[a.evidence.id]), reverse('evidence-reject', args=[a.evidence.id]),
            reverse('evidence-override', args=[a.evidence.id]), reverse('attendance-approve', args=[a.attendance.id]),
            reverse('attendance-reject', args=[a.attendance.id]), reverse('od-request-approve', args=[a.od.id]),
            reverse('od-request-reject', args=[a.od.id]), reverse('achievement-approve', args=[a.achievement.id]),
            reverse('achievement-reject', args=[a.achievement.id]), reverse('achievement-submit',
                                                                            args=[a.achievement.id]),
        ):
            response = self.client.post(url, {'reason': 'x', 'decision': 'VERIFIED'})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, url)
        response = self.client.patch(reverse('achievement-detail', args=[a.achievement.id]), {'title': 'hacked'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class CrossDepartmentIdorTests(AuthMixin, APITestCase):
    """Department B staff against department A's records."""

    def setUp(self):
        self.u = build_universe()

    def test_faculty_and_event_coordinator_of_b_get_404_on_a_records(self):
        a = self.u.a
        urls = [
            reverse('registration-detail', args=[a.registration.id]),
            reverse('participation-detail', args=[a.participation.id]),
            reverse('evidence-detail', args=[a.evidence.id]),
            reverse('evidence-capture-image', args=[a.capture.id]),
            reverse('attendance-detail', args=[a.attendance.id]),
            reverse('od-request-detail', args=[a.od.id]),
            reverse('achievement-detail', args=[a.achievement.id]),
        ]
        for username in ('facultyb', 'hodb'):
            self._auth_as(username)
            for url in urls:
                self.assertEqual(self.client.get(url).status_code, status.HTTP_404_NOT_FOUND, f'{username} {url}')

    def test_department_b_staff_cannot_decide_department_a_records(self):
        a = self.u.a
        self._auth_as('facultyb')
        for url in (reverse('evidence-verify', args=[a.evidence.id]), reverse('evidence-reject', args=[a.evidence.id])):
            self.assertEqual(self.client.post(url, {'reason': 'x'}).status_code, status.HTTP_404_NOT_FOUND, url)
        for url, body in (
            (reverse('attendance-list'), {'participation': a.participation.id}),
            (reverse('od-request-list'), {'participation': a.participation.id, 'reason': 'x'}),
            (reverse('achievement-list'), {'participation': a.participation.id, 'title': 'x',
                                           'achievement_type': 'x', 'achievement_date': str(a.event.event_date)}),
        ):
            self.assertEqual(self.client.post(url, body).status_code, status.HTTP_404_NOT_FOUND, url)
        self._auth_as('hodb')
        for url in (
            reverse('evidence-override', args=[a.evidence.id]), reverse('attendance-approve', args=[a.attendance.id]),
            reverse('od-request-approve', args=[a.od.id]), reverse('achievement-approve', args=[a.achievement.id]),
        ):
            response = self.client.post(url, {'reason': 'x', 'decision': 'VERIFIED'})
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, url)
        self.assertEqual(
            self.client.patch(reverse('event-detail', args=[a.event.id]), {'title': 'Taken over'}).status_code,
            # Published events are visible to every Event Coordinator, so this is a visible-but-forbidden 403.
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(self.client.get(reverse('event-detail', args=[a.draft_event.id])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse('event-publish', args=[a.draft_event.id])).status_code, status.HTTP_404_NOT_FOUND,
        )

    def test_event_coordinator_b_cannot_see_department_a_through_filters(self):
        a = self.u.a
        self._auth_as('hodb')
        self.assertEqual(self.client.get(reverse('registration-list'), {'event': a.event.id}).data['count'], 0)
        self.assertEqual(self.client.get(reverse('auditlog-list'), {'actor': a.faculty.id}).data['count'], 0)
        self.assertEqual(self.client.get(reverse('analytics-overview'), {'department': a.department.id}).status_code,
                         403)
        self.assertEqual(self.client.get(reverse('analytics-overview'), {'student': a.student.id}).status_code, 403)
        self.assertEqual(self.client.get(reverse('analytics-overview'), {'event': a.event.id}).status_code, 404)
        self.assertEqual(self.client.get(reverse('report-preview', args=['department']),
                                         {'department': a.department.id}).status_code, 403)
        self.assertEqual(self.client.get(reverse('ai-anomalies'), {'evidence': a.evidence.id}).status_code, 404)

    def test_faculty_cannot_perform_event_coordinator_decisions_even_in_own_department(self):
        a = self.u.a
        self._auth_as('facultya')
        for url in (
            reverse('evidence-override', args=[a.evidence.id]), reverse('attendance-approve', args=[a.attendance.id]),
            reverse('attendance-reject', args=[a.attendance.id]), reverse('od-request-approve', args=[a.od.id]),
            reverse('achievement-approve', args=[a.achievement.id]), reverse('achievement-reject',
                                                                             args=[a.achievement.id]),
        ):
            response = self.client.post(url, {'reason': 'x', 'decision': 'VERIFIED'})
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, url)

    def test_pinned_deviation_registration_request_review_is_403_not_404(self):
        """Documented: the registration-request reviewer view reveals that a
        request exists in another department (403). Pinned here so a change
        is deliberate."""
        from apps.accounts.models import RegistrationRequest
        request = RegistrationRequest.objects.create(
            user=self.u.a.other_student, role='STUDENT', department=self.u.a.department,
        )
        self._auth_as('hodb')
        response = self.client.post(reverse('registration-request-approve', args=[request.id]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        request.refresh_from_db()
        self.assertEqual(request.status, RegistrationRequest.Status.PENDING)


class NonexistentAndMalformedIdTests(AuthMixin, APITestCase):
    def setUp(self):
        self.u = build_universe()

    def test_nonexistent_ids_are_404_for_admin_too(self):
        self._auth_as('sysadmin')
        for name in ('registration-detail', 'participation-detail', 'evidence-detail', 'attendance-detail',
                     'od-request-detail', 'achievement-detail', 'notification-detail', 'event-detail',
                     'evidence-capture-image'):
            self.assertEqual(self.client.get(reverse(name, args=[999999])).status_code, 404, name)
        for name in ('evidence-version-captures', 'evidence-version-submit'):
            self.assertEqual(self.client.post(reverse(name, args=[999999]), {}).status_code, 404, name)

    def test_non_numeric_ids_never_match_a_route_or_500(self):
        self._auth_as('sysadmin')
        for path in ('/api/v1/events/abc/', '/api/v1/evidence/abc/', '/api/v1/attendance/%27/',
                     '/api/v1/evidence/captures/abc/image/', '/api/v1/evidence/versions/abc/submit/'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, path)
