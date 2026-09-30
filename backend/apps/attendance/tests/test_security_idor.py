"""
IDOR and field-spoofing coverage for attendance, following the project's
standing convention: a record outside the requester's visible queryset -> 404
(never confirming it exists); a visible record with a forbidden action for
that role -> 403.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance

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


class AttendanceIdorTests(AuthMixin, APITestCase):
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
        self.attendance_a = Attendance.objects.create(
            participation=self.participation_a, requested_by=self.faculty_cs,
        )
        self.list_url = reverse('attendance-list')
        self.detail_a = reverse('attendance-detail', args=[self.attendance_a.id])

    # --- student isolation --------------------------------------------------

    def test_student_cannot_read_another_students_attendance(self):
        self._auth_as('studentb')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_404_NOT_FOUND)

    def test_student_list_only_contains_their_own_records(self):
        self._auth_as('studenta')
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([row['id'] for row in response.data['results']], [self.attendance_a.id])

        self._auth_as('studentb')
        response = self.client.get(self.list_url)
        self.assertEqual(response.data['results'], [])

    def test_student_cannot_create_attendance_for_another_student(self):
        self._auth_as('studentb')
        response = self.client.post(self.list_url, {'participation': self.participation_a.id})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # --- cross-department ---------------------------------------------------

    def test_faculty_from_another_department_cannot_read_the_record(self):
        self._auth_as('facultyec')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_404_NOT_FOUND)

    def test_faculty_from_another_department_cannot_request_for_this_participation(self):
        self._auth_as('facultyec')
        response = self.client.post(self.list_url, {'participation': self.participation_b.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_coordinator_from_another_department_cannot_approve(self):
        self._auth_as('hodec')
        response = self.client.post(reverse('attendance-approve', args=[self.attendance_a.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Attendance.objects.get(pk=self.attendance_a.id).status, Attendance.Status.PENDING)

    def test_event_coordinator_from_another_department_sees_an_empty_queue(self):
        self._auth_as('hodec')
        response = self.client.get(self.list_url)
        self.assertEqual(response.data['results'], [])

    def test_admin_can_read_system_wide(self):
        self._auth_as('sysadmin')
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_200_OK)

    # --- field spoofing -----------------------------------------------------

    def test_client_cannot_spoof_status_reviewer_or_timestamps_on_create(self):
        self._auth_as('facultycs')
        response = self.client.post(self.list_url, {
            'participation': self.participation_b.id,
            'status': 'APPROVED',
            'reviewed_by': self.event_coordinator_cs.id,
            'reviewed_at': '2020-01-01T00:00:00Z',
            'requested_at': '2020-01-01T00:00:00Z',
            'rejection_reason': 'injected',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        created = Attendance.objects.get(pk=response.data['id'])
        self.assertEqual(created.status, Attendance.Status.PENDING)
        self.assertIsNone(created.reviewed_by_id)
        self.assertIsNone(created.reviewed_at)
        self.assertEqual(created.rejection_reason, '')
        self.assertGreater(created.requested_at.year, 2020)

    def test_there_is_no_update_endpoint_to_set_status_directly(self):
        self._auth_as('hodcs')
        for method in (self.client.patch, self.client.put):
            response = method(self.detail_a, {'status': 'APPROVED'})
            self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(Attendance.objects.get(pk=self.attendance_a.id).status, Attendance.Status.PENDING)

    def test_reviewer_is_always_the_authenticated_user_not_a_supplied_one(self):
        self._auth_as('hodcs')
        response = self.client.post(
            reverse('attendance-approve', args=[self.attendance_a.id]),
            {'reviewed_by': self.faculty_cs.id, 'reviewed_at': '2020-01-01T00:00:00Z'},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        refreshed = Attendance.objects.get(pk=self.attendance_a.id)
        self.assertEqual(refreshed.reviewed_by_id, self.event_coordinator_cs.id)
        self.assertGreater(refreshed.reviewed_at.year, 2020)

    def test_unauthenticated_access_is_rejected(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.list_url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(self.client.get(self.detail_a).status_code, status.HTTP_401_UNAUTHORIZED)


class DepartmentlessStaffTests(AuthMixin, APITestCase):
    """A staff account with no department must not implicitly match a
    department-less (Admin-created) event's records. `NULL = NULL` comparing
    equal is exactly the kind of accidental grant this guards against; the
    same guard is applied identically in the OD and achievements apps."""

    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('nodeptstudent', self.cs)

        # An Admin-created event has no department at all.
        self.admin = make_admin('sysadmin')
        self.event = make_todays_published_event(
            created_by=self.admin, college=self.college, department=None,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )
        self.attendance = Attendance.objects.create(
            participation=self.participation, requested_by=self.faculty,
        )

        # A Faculty and an Event Coordinator with no department of their own.
        self.rogue_faculty = make_faculty('roguefaculty', None)
        self.rogue_event_coordinator = make_event_coordinator('roguehod', None)

    def test_departmentless_faculty_sees_an_empty_queue(self):
        self._auth_as('roguefaculty')
        response = self.client.get(reverse('attendance-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'], [])

    def test_departmentless_faculty_cannot_read_the_record(self):
        self._auth_as('roguefaculty')
        response = self.client.get(reverse('attendance-detail', args=[self.attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_departmentless_faculty_cannot_request_attendance(self):
        self._auth_as('roguefaculty')
        response = self.client.post(reverse('attendance-list'), {'participation': self.participation.id})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_departmentless_event_coordinator_cannot_approve(self):
        self._auth_as('roguehod')
        response = self.client.post(reverse('attendance-approve', args=[self.attendance.id]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Attendance.objects.get(pk=self.attendance.id).status, Attendance.Status.PENDING)
