"""
Real cross-connection concurrency (TransactionTestCase + threads — a plain
TestCase wraps everything in one rollback-only transaction and cannot exercise
a genuine race).
"""

import threading

from django.db import connection
from django.test import TransactionTestCase

from apps.attendance import services
from apps.attendance.models import Attendance

from .helpers import (
    make_college,
    make_department,
    make_faculty,
    make_event_coordinator,
    make_student,
    make_todays_published_event,
    make_verified_participation,
)


class _Fixture:
    def build(self):
        college = make_college()
        department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', department)
        self.hod2 = make_event_coordinator('hodcs2', make_department('CS2', 'Computer Science II'))
        self.faculty = make_faculty('facultycs', department)
        student = make_student('racestudent', department)
        event = make_todays_published_event(created_by=self.event_coordinator, college=college, department=department)
        self.participation = make_verified_participation(
            student=student, event=event, reviewer=self.faculty,
        )


class ConcurrentAttendanceRequestTests(TransactionTestCase, _Fixture):
    def test_two_simultaneous_requests_create_only_one_record(self):
        self.build()
        results = []

        def attempt():
            try:
                services.request_attendance(participation=self.participation, requested_by=self.faculty)
                results.append('created')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count('created'), 1, results)
        self.assertEqual(results.count('blocked'), 1, results)
        self.assertEqual(Attendance.objects.filter(participation=self.participation).count(), 1)


class ConcurrentAttendanceDecisionTests(TransactionTestCase, _Fixture):
    def test_two_simultaneous_approvals_only_one_wins(self):
        self.build()
        attendance = services.request_attendance(
            participation=self.participation, requested_by=self.faculty,
        )
        results = []

        def attempt(reviewer):
            try:
                services.approve_attendance(attendance=attendance, reviewer=reviewer)
                results.append('approved')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt, args=(self.event_coordinator,))
        t2 = threading.Thread(target=attempt, args=(self.event_coordinator,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.count('approved'), 1, results)
        self.assertEqual(results.count('blocked'), 1, results)
        refreshed = Attendance.objects.get(pk=attendance.pk)
        self.assertEqual(refreshed.status, Attendance.Status.APPROVED)
        self.assertIsNotNone(refreshed.reviewed_by_id)

    def test_simultaneous_approve_and_reject_leave_exactly_one_outcome(self):
        self.build()
        attendance = services.request_attendance(
            participation=self.participation, requested_by=self.faculty,
        )
        results = []

        def approve():
            try:
                services.approve_attendance(attendance=attendance, reviewer=self.event_coordinator)
                results.append('approved')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        def reject():
            try:
                services.reject_attendance(attendance=attendance, reviewer=self.event_coordinator, reason='no')
                results.append('rejected')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        t1 = threading.Thread(target=approve)
        t2 = threading.Thread(target=reject)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(results.count('blocked'), 1, results)
        refreshed = Attendance.objects.get(pk=attendance.pk)
        self.assertIn(refreshed.status, (Attendance.Status.APPROVED, Attendance.Status.REJECTED))
        self.assertIsNotNone(refreshed.reviewed_at)
