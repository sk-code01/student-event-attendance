import threading

from django.db import connection
from django.test import TransactionTestCase

from apps.participation.models import Participation

from .helpers import (
    make_college, make_department, make_event_coordinator, make_registration, make_student, make_todays_published_event,
)


class ConcurrentParticipationOpenTests(TransactionTestCase):
    """Real cross-connection concurrency (TransactionTestCase, not TestCase
    — see apps/registrations/tests/test_race_condition.py for why this
    matters): two threads racing to open a Participation for the same
    registration must never both succeed in creating a row."""

    def test_concurrent_open_creates_only_one_participation(self):
        college = make_college()
        department = make_department('CS', 'Computer Science')
        event_coordinator = make_event_coordinator('hodcs', department)
        student = make_student('racestudent', department)
        event = make_todays_published_event(created_by=event_coordinator, college=college, department=department)
        registration = make_registration(student=student, event=event)

        results = []

        def attempt():
            try:
                Participation.objects.create(registration=registration)
                results.append('created')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt)
        t2 = threading.Thread(target=attempt)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(results), ['blocked', 'created'])
        self.assertEqual(Participation.objects.filter(registration=registration).count(), 1)
