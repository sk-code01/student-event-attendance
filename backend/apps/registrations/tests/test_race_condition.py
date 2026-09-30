import threading

from django.db import IntegrityError, connection
from django.test import TransactionTestCase

from apps.events.models import Event
from apps.registrations.models import Registration

from .helpers import make_college, make_department, make_event, make_event_coordinator, make_student


class ConcurrentRegistrationTests(TransactionTestCase):
    """Uses TransactionTestCase (real commits, no outer-transaction rollback)
    so two threads with independent DB connections genuinely race against
    the database's unique constraint — a plain TestCase's transaction
    wrapping would not exercise real concurrency."""

    def test_concurrent_duplicate_registration_creates_only_one_row(self):
        college = make_college()
        department = make_department('CS', 'Computer Science')
        event_coordinator = make_event_coordinator('hodcs', department)
        student = make_student('studentcs', department)
        event = make_event(
            created_by=event_coordinator, college=college, department=department, status=Event.Status.PUBLISHED,
        )

        outcomes = []

        def attempt_registration():
            try:
                Registration.objects.create(student=student, event=event)
                outcomes.append('created')
            except IntegrityError:
                outcomes.append('blocked')
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt_registration)
        t2 = threading.Thread(target=attempt_registration)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(outcomes), ['blocked', 'created'])
        self.assertEqual(Registration.objects.filter(student=student, event=event).count(), 1)
