"""
Attendance and OD are independent academic decisions.

This is the file that would fail loudly if anyone ever "helpfully" coupled the
two — e.g. by refusing OD when attendance exists, by cascading a rejection, or
by modelling OD as an attendance status.
"""

from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.od.models import ODRequest

from .helpers import (
    AuthMixin,
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)


class AttendanceAndODIndependenceTests(AuthMixin, APITestCase):
    def setUp(self):
        self.college = make_college()
        self.cs = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.cs)
        self.faculty = make_faculty('facultycs', self.cs)
        self.student = make_student('indstudent', self.cs)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.cs,
        )
        self.participation = make_verified_participation(
            student=self.student, event=self.event, reviewer=self.faculty,
        )

    def _request_both(self):
        self._auth_as('facultycs')
        attendance = self.client.post(reverse('attendance-list'), {'participation': self.participation.id})
        self.assertEqual(attendance.status_code, status.HTTP_201_CREATED, attendance.data)
        od = self.client.post(
            reverse('od-request-list'), {'participation': self.participation.id, 'reason': 'Both apply'},
        )
        self.assertEqual(od.status_code, status.HTTP_201_CREATED, od.data)
        return attendance.data['id'], od.data['id']

    def test_both_can_exist_for_the_same_participation(self):
        attendance_id, od_id = self._request_both()
        self.assertTrue(Attendance.objects.filter(pk=attendance_id).exists())
        self.assertTrue(ODRequest.objects.filter(pk=od_id).exists())

    def test_existing_attendance_does_not_block_an_od_request(self):
        self._auth_as('facultycs')
        self.client.post(reverse('attendance-list'), {'participation': self.participation.id})
        response = self.client.post(
            reverse('od-request-list'), {'participation': self.participation.id, 'reason': 'still valid'},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)

    def test_approving_attendance_leaves_the_od_request_untouched(self):
        attendance_id, od_id = self._request_both()
        self._auth_as('hodcs')
        self.client.post(reverse('attendance-approve', args=[attendance_id]))
        self.assertEqual(Attendance.objects.get(pk=attendance_id).status, Attendance.Status.APPROVED)
        self.assertEqual(ODRequest.objects.get(pk=od_id).status, ODRequest.Status.PENDING)

    def test_rejecting_od_leaves_approved_attendance_untouched(self):
        attendance_id, od_id = self._request_both()
        self._auth_as('hodcs')
        self.client.post(reverse('attendance-approve', args=[attendance_id]))
        self.client.post(reverse('od-request-reject', args=[od_id]), {'reason': 'OD not applicable'})

        self.assertEqual(Attendance.objects.get(pk=attendance_id).status, Attendance.Status.APPROVED)
        self.assertEqual(ODRequest.objects.get(pk=od_id).status, ODRequest.Status.REJECTED)

    def test_rejecting_attendance_does_not_prevent_od_approval(self):
        """The opposite outcomes on the same participation must both stand —
        they are different decisions, not two views of one decision."""
        attendance_id, od_id = self._request_both()
        self._auth_as('hodcs')
        self.client.post(reverse('attendance-reject', args=[attendance_id]), {'reason': 'attendance not applicable'})
        response = self.client.post(reverse('od-request-approve', args=[od_id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(Attendance.objects.get(pk=attendance_id).status, Attendance.Status.REJECTED)
        self.assertEqual(ODRequest.objects.get(pk=od_id).status, ODRequest.Status.APPROVED)

    def test_od_is_not_modelled_as_an_attendance_status(self):
        self.assertNotIn('OD', Attendance.Status.values)
        self.assertNotIn('OD', [label.upper() for label in Attendance.Status.labels])
