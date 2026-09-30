"""The department-wide tracking view (requirements 8, 9, 10, 15 and 17)."""


from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.attendance.models import Attendance
from apps.certificates.models import Certificate
from apps.certificates.tests.helpers import make_past_event, make_pdf_upload
from apps.certificates.services import submit_certificate
from apps.participation.models import Participation
from apps.registrations.models import Registration
from apps.verification.models import Evidence
from apps.verification.tests.helpers import (
    make_college,
    make_department,
    make_event,
    make_event_coordinator,
    make_faculty,
    make_participation,
    make_student,
    make_submitted_evidence,
)


class TrackingTestBase(APITestCase):
    def setUp(self):
        self.department = make_department('CS', 'Computer Science')
        self.college = make_college()
        self.coordinator = make_event_coordinator('ec1', self.department)
        self.faculty = make_faculty('fac1', self.department)
        self.url = reverse('registration-tracking')

        # One student who captured, one who did not — the two states the
        # coordinator most needs to tell apart.
        self.captured = make_student('captured1', self.department, university_registration_number='1AY22MC001')
        self.absent = make_student('absent1', self.department, university_registration_number='1AY22MC002')
        self.event = make_past_event(college=self.college, department=self.department)

        self.captured_participation = make_participation(student=self.captured, event=self.event)
        make_submitted_evidence(participation=self.captured_participation)
        self.absent_registration = Registration.objects.create(student=self.absent, event=self.event)

    def rows_for(self, user, **params):
        self.client.force_authenticate(user)
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        return response.data['results'] if 'results' in response.data else response.data

    def row_of(self, rows, username):
        return next(row for row in rows if row['student']['username'] == username)


class CoordinatorVisibilityTests(TrackingTestBase):
    def test_the_coordinator_sees_every_registration_in_their_department(self):
        rows = self.rows_for(self.coordinator)
        self.assertEqual({row['student']['username'] for row in rows}, {'captured1', 'absent1'})

    def test_rows_carry_the_student_identity_and_registration_number(self):
        row = self.row_of(self.rows_for(self.coordinator), 'captured1')
        self.assertEqual(row['student']['university_registration_number'], '1AY22MC001')
        self.assertEqual(row['student']['full_name'], 'Captured1')

    def test_a_student_who_never_captured_is_reported_as_not_submitted(self):
        row = self.row_of(self.rows_for(self.coordinator), 'absent1')
        self.assertEqual(row['live_capture_status'], 'NOT_SUBMITTED')
        self.assertIsNone(row['participation_status'])

    def test_a_student_who_captured_is_reported_as_submitted(self):
        row = self.row_of(self.rows_for(self.coordinator), 'captured1')
        self.assertEqual(row['live_capture_status'], 'SUBMITTED')
        self.assertEqual(row['participation_status'], Participation.Status.SUBMITTED)

    def test_registration_alone_never_reports_attendance(self):
        for row in self.rows_for(self.coordinator):
            self.assertEqual(row['attendance_status'], 'NOT_RECORDED')

    def test_another_departments_registrations_are_not_visible(self):
        other_department = make_department('EC', 'Electronics')
        other_coordinator = make_event_coordinator('ec2', other_department)

        self.assertEqual(self.rows_for(other_coordinator), [])


class DerivedStatusTests(TrackingTestBase):
    def test_a_future_event_is_awaiting_rather_than_missing(self):
        future_event = make_event(
            created_by=self.coordinator, college=self.college, department=self.department,
            days_until_event=7,
        )
        Registration.objects.create(student=self.absent, event=future_event)

        rows = self.rows_for(self.coordinator, event=future_event.id)
        self.assertEqual(rows[0]['live_capture_status'], 'AWAITING_EVENT')

    def test_verification_status_follows_the_evidence(self):
        Evidence.objects.filter(participation=self.captured_participation).update(
            status=Evidence.Status.VERIFIED,
        )
        row = self.row_of(self.rows_for(self.coordinator), 'captured1')
        self.assertEqual(row['verification_status'], 'VERIFIED')

    def test_certificate_is_not_eligible_without_a_live_capture(self):
        row = self.row_of(self.rows_for(self.coordinator), 'absent1')
        self.assertEqual(row['certificate_status'], 'NOT_ELIGIBLE')
        self.assertEqual(row['certificate_attempts_remaining'], 0)

    def test_certificate_status_and_attempts_are_reported(self):
        submit_certificate(
            participation=self.captured_participation, user=self.captured,
            uploaded_file=make_pdf_upload(),
        )
        row = self.row_of(self.rows_for(self.coordinator), 'captured1')
        self.assertEqual(row['certificate_status'], Certificate.Status.SUBMITTED)
        self.assertEqual(row['certificate_attempts_used'], 1)
        self.assertEqual(row['certificate_attempts_remaining'], 2)

    def test_manual_attendance_is_shown_as_manual_and_names_who_set_it(self):
        Attendance.objects.create(
            registration=self.absent_registration, status=Attendance.Status.APPROVED,
            is_manual=True, reviewed_by=self.coordinator, reviewed_at=timezone.now(),
        )
        row = self.row_of(self.rows_for(self.coordinator), 'absent1')
        self.assertEqual(row['attendance_status'], 'APPROVED')
        self.assertTrue(row['attendance_is_manual'])
        self.assertEqual(row['attendance_decided_by'], 'ec1')


class FilteringTests(TrackingTestBase):
    def test_filter_by_live_capture_status(self):
        rows = self.rows_for(self.coordinator, live_capture_status='NOT_SUBMITTED')
        self.assertEqual([row['student']['username'] for row in rows], ['absent1'])

    def test_filter_by_attendance_status(self):
        rows = self.rows_for(self.coordinator, attendance_status='NOT_RECORDED')
        self.assertEqual(len(rows), 2)

    def test_search_matches_the_registration_number(self):
        rows = self.rows_for(self.coordinator, search='1AY22MC002')
        self.assertEqual([row['student']['username'] for row in rows], ['absent1'])

    def test_search_matches_the_full_name(self):
        rows = self.rows_for(self.coordinator, search='Captured1')
        self.assertEqual([row['student']['username'] for row in rows], ['captured1'])

    def test_filter_by_event(self):
        rows = self.rows_for(self.coordinator, event=self.event.id)
        self.assertEqual(len(rows), 2)

    def test_a_non_numeric_student_filter_is_a_client_error(self):
        self.client.force_authenticate(self.coordinator)
        response = self.client.get(self.url, {'student': 'abc'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class StudentHistoryTests(TrackingTestBase):
    def test_narrowing_to_one_student_gives_their_history_in_date_order(self):
        earlier = make_past_event(college=self.college, department=self.department, days_ago=30)
        Registration.objects.create(student=self.absent, event=earlier)

        rows = self.rows_for(self.coordinator, student=self.absent.id)
        dates = [row['event']['event_date'] for row in rows]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(rows), 2)

    def test_a_student_sees_only_their_own_history(self):
        rows = self.rows_for(self.captured)
        self.assertEqual({row['student']['username'] for row in rows}, {'captured1'})


class FacultyVisibilityTests(TrackingTestBase):
    def test_faculty_can_see_their_departments_registered_students(self):
        rows = self.rows_for(self.faculty)
        self.assertEqual({row['student']['username'] for row in rows}, {'captured1', 'absent1'})

    def test_faculty_from_another_department_see_nothing(self):
        other_department = make_department('EC', 'Electronics')
        outsider = make_faculty('fac2', other_department)
        self.assertEqual(self.rows_for(outsider), [])

    def test_an_anonymous_caller_is_rejected(self):
        self.client.force_authenticate(None)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
