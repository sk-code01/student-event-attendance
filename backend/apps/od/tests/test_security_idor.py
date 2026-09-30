"""IDOR and field-spoofing coverage for OD — same 404/403 convention as
everywhere else in this project."""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.od.models import ODRequest

from .helpers import (
    AuthMixin,
    make_admin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)


class ODIdorTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.ec = make_department('EC', 'Electronics')

        self.event_coordinator_cs = make_event_coordinator('hodcs', self.cs)
        self.event_coordinator_ec = make_event_coordinator('hodec', self.ec)
        self.faculty_cs = make_faculty('facultycs', self.cs)
        self.faculty_ec = make_faculty('facultyec', self.ec)
        self.admin = make_admin('sysadmin')

        self.student_a = make_student('studenta', self.cs)
        self.student_b = make_student('studentb', self.cs)

        self.event = make_todays_published_event(
            created_by=self.event_coordinator_cs, college=self.college, department=self.cs,
        )
        self.participation_a = make_verified_participation(
            student=self.student_a, event=self.event, reviewer=self.faculty_cs,
        )
        self.participation_b = make_verified_participation(
            student=self.student_b, event=self.event, reviewer=self.faculty_cs,
        )
        self.od_a = ODRequest.objects.create(
            participation=self.participation_a, requested_by=self.faculty_cs, reason='conference',
        )
        self.list_url = reverse('od-request-list')
        self.detail_a = reverse('od-request-detail', args=[self.od_a.id])

    def test_student_cannot_read_another_students_od(self):
        self._auth_as('studentb')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_404_NOT_FOUND)

    def test_student_list_only_contains_their_own_records(self):
        self._auth_as('studenta')
        response = self.client.get(self.list_url)
        self.assertEqual([row['id'] for row in response.data['results']], [self.od_a.id])
        self._auth_as('studentb')
        self.assertEqual(self.client.get(self.list_url).data['results'], [])

    def test_student_cannot_create_od_for_another_student(self):
        self._auth_as('studentb')
        response = self.client.post(self.list_url, {'participation': self.participation_a.id, 'reason': 'x'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_faculty_from_another_department_cannot_read_or_request(self):
        self._auth_as('facultyec')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_404_NOT_FOUND)
        response = self.client.post(self.list_url, {'participation': self.participation_b.id, 'reason': 'x'})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_coordinator_from_another_department_cannot_approve_or_see_the_queue(self):
        self._auth_as('hodec')
        response = self.client.post(reverse('od-request-approve', args=[self.od_a.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(self.client.get(self.list_url).data['results'], [])
        self.assertEqual(ODRequest.objects.get(pk=self.od_a.id).status, ODRequest.Status.PENDING)

    def test_client_cannot_spoof_status_reviewer_or_timestamps_on_create(self):
        self._auth_as('facultycs')
        response = self.client.post(self.list_url, {
            'participation': self.participation_b.id,
            'reason': 'legit reason',
            'status': 'APPROVED',
            'reviewed_by': self.event_coordinator_cs.id,
            'reviewed_at': '2020-01-01T00:00:00Z',
            'rejection_reason': 'injected',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = ODRequest.objects.get(pk=response.data['id'])
        self.assertEqual(created.status, ODRequest.Status.PENDING)
        self.assertIsNone(created.reviewed_by_id)
        self.assertIsNone(created.reviewed_at)
        self.assertEqual(created.rejection_reason, '')

    def test_there_is_no_update_endpoint_to_set_status_directly(self):
        self._auth_as('hodcs')
        for method in (self.client.patch, self.client.put):
            self.assertEqual(
                method(self.detail_a, {'status': 'APPROVED'}).status_code, status.HTTP_405_METHOD_NOT_ALLOWED,
            )

    def test_reviewer_is_always_the_authenticated_user(self):
        self._auth_as('hodcs')
        response = self.client.post(
            reverse('od-request-approve', args=[self.od_a.id]),
            {'reviewed_by': self.faculty_cs.id, 'reviewed_at': '2020-01-01T00:00:00Z'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        refreshed = ODRequest.objects.get(pk=self.od_a.id)
        self.assertEqual(refreshed.reviewed_by_id, self.event_coordinator_cs.id)
        self.assertGreater(refreshed.reviewed_at.year, 2020)

    def test_admin_can_read_system_wide(self):
        self._auth_as('sysadmin')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_200_OK)

    def test_unauthenticated_access_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
