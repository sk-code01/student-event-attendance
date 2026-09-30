"""Real cross-connection concurrency for the OD workflow."""

import threading

from django.db import connection
from django.test import TransactionTestCase

from apps.od import services
from apps.od.models import ODRequest

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
        self.faculty = make_faculty('facultycs', department)
        student = make_student('odracestudent', department)
        event = make_todays_published_event(created_by=self.event_coordinator, college=college, department=department)
        self.participation = make_verified_participation(
            student=student, event=event, reviewer=self.faculty,
        )


class ConcurrentODRequestTests(TransactionTestCase, _Fixture):
    def test_two_simultaneous_requests_create_only_one_record(self):
        self.build()
        results = []

        def attempt():
            try:
                services.request_od(
                    participation=self.participation, requested_by=self.faculty, reason='fest',
                )
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
        self.assertEqual(ODRequest.objects.filter(participation=self.participation).count(), 1)


class ConcurrentODDecisionTests(TransactionTestCase, _Fixture):
    def test_two_simultaneous_approvals_only_one_wins(self):
        self.build()
        od_request = services.request_od(
            participation=self.participation, requested_by=self.faculty, reason='fest',
        )
        results = []

        def attempt():
            try:
                services.approve_od(od_request=od_request, reviewer=self.event_coordinator)
                results.append('approved')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(results.count('approved'), 1, results)
        self.assertEqual(results.count('blocked'), 1, results)
        self.assertEqual(ODRequest.objects.get(pk=od_request.pk).status, ODRequest.Status.APPROVED)
