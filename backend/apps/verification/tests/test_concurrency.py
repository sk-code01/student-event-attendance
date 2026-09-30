import threading

from django.db import connection
from django.test import TransactionTestCase

from apps.verification import services
from apps.verification.models import Evidence, EvidenceVerification, EvidenceVersion

from .helpers import (
    make_college, make_department, make_faculty, make_event_coordinator, make_participation, make_student,
    make_submitted_evidence, make_todays_published_event,
)


class ConcurrentVersionCreationTests(TransactionTestCase):
    """Real cross-connection concurrency: two threads racing to open a new
    resubmission version for the same evidence must never both create
    version 2 — the row lock taken in services._lock_or_create_evidence
    serializes them."""

    def test_concurrent_resubmission_open_creates_only_one_version_two(self):
        college = make_college()
        department = make_department('CS', 'Computer Science')
        event_coordinator = make_event_coordinator('hodcs', department)
        faculty = make_faculty('facultycs', department)
        student = make_student('racestudent', department)
        event = make_todays_published_event(created_by=event_coordinator, college=college, department=department)
        participation = make_participation(student=student, event=event)
        evidence, version1 = make_submitted_evidence(participation=participation)
        EvidenceVerification.objects.create(
            evidence_version=version1, reviewer=faculty, decision=EvidenceVerification.Decision.RESUBMISSION_REQUIRED,
            reason='retake needed',
        )
        Evidence.objects.filter(pk=evidence.pk).update(status=Evidence.Status.RESUBMISSION_REQUIRED)

        results = []

        def attempt():
            try:
                services.open_evidence_version(participation=participation, user=student)
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

        self.assertEqual(results.count('created'), 2)  # both succeed: idempotent get-or-create semantics
        version_numbers = list(
            EvidenceVersion.objects.filter(evidence=evidence).order_by('version_number').values_list('version_number',
                                                                                                     flat=True),
        )
        self.assertEqual(version_numbers, [1, 2])


class ConcurrentDecisionTests(TransactionTestCase):
    """Two Faculty accounts racing to decide the same evidence must not
    both succeed in recording a decision — the second is rejected once the
    row-locked transaction observes the evidence is no longer
    SUBMITTED/UNDER_REVIEW."""

    def test_concurrent_faculty_decisions_only_one_wins(self):
        college = make_college()
        department = make_department('CS', 'Computer Science')
        event_coordinator = make_event_coordinator('hodcs', department)
        faculty1 = make_faculty('faculty1', department)
        faculty2 = make_faculty('faculty2', department)
        student = make_student('decisionstudent', department)
        event = make_todays_published_event(created_by=event_coordinator, college=college, department=department)
        participation = make_participation(student=student, event=event)
        evidence, version = make_submitted_evidence(participation=participation)

        results = []

        def attempt(reviewer):
            try:
                services.record_faculty_decision(
                    evidence=evidence, reviewer=reviewer, decision=EvidenceVerification.Decision.VERIFIED, reason='',
                )
                results.append('decided')
            except Exception:
                results.append('blocked')
            finally:
                connection.close()

        t1 = threading.Thread(target=attempt, args=(faculty1,))
        t2 = threading.Thread(target=attempt, args=(faculty2,))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(sorted(results), ['blocked', 'decided'])
        self.assertEqual(EvidenceVerification.objects.filter(evidence_version=version).count(), 1)
