from django.db import IntegrityError
from django.test import TestCase

from apps.participation.models import Participation

from .helpers import make_college, make_department, make_event_coordinator, make_registered_student_for_today


class ParticipationUniquenessTests(TestCase):
    """EvidenceCapture-level model tests moved to apps.verification.tests
    (that model no longer lives in apps.participation as of Phase 4)."""

    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.student, self.event, self.registration = make_registered_student_for_today(
            event_coordinator=self.event_coordinator, department=self.department, college=self.college,
        )

    def test_one_participation_per_registration(self):
        Participation.objects.create(registration=self.registration)
        with self.assertRaises(IntegrityError):
            Participation.objects.create(registration=self.registration)

    def test_student_and_event_are_auto_derived_from_registration(self):
        participation = Participation.objects.create(registration=self.registration)
        self.assertEqual(participation.student_id, self.student.id)
        self.assertEqual(participation.event_id, self.event.id)
