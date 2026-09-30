from django.db import IntegrityError
from django.test import TestCase

from apps.verification.models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion

from .helpers import (
    make_college, make_department, make_faculty, make_event_coordinator, make_participation, make_student,
    make_todays_published_event, make_uploaded_image, noon_on,
)


class EvidenceCaptureUniquenessTests(TestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.student = make_student('modelstudent', self.department)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)
        self.evidence = Evidence.objects.create(participation=self.participation)
        self.version = EvidenceVersion.objects.create(evidence=self.evidence, version_number=1,
                                                      submitted_by=self.student)

    def _make_capture(self, role):
        return EvidenceCapture.objects.create(
            evidence_version=self.version, capture_role=role,
            object_reference=make_uploaded_image(), mime_type='image/jpeg', file_size=100, sha256_hash='a' * 64,
            device_capture_timestamp=noon_on(self.event.event_date), latitude=1, longitude=1, gps_accuracy=10,
        )

    def test_only_one_primary_capture_allowed_per_version(self):
        self._make_capture(EvidenceCapture.Role.PRIMARY)
        with self.assertRaises(IntegrityError):
            self._make_capture(EvidenceCapture.Role.PRIMARY)

    def test_multiple_additional_captures_allowed(self):
        self._make_capture(EvidenceCapture.Role.ADDITIONAL)
        self._make_capture(EvidenceCapture.Role.ADDITIONAL)
        self.assertEqual(
            EvidenceCapture.objects.filter(evidence_version=self.version,
                                           capture_role=EvidenceCapture.Role.ADDITIONAL).count(),
            2,
        )

    def test_capture_upload_path_ignores_client_filename(self):
        capture = self._make_capture(EvidenceCapture.Role.PRIMARY)
        self.assertNotIn('capture.jpg', capture.object_reference.name)
        self.assertTrue(capture.object_reference.name.endswith('.jpg'))

    def test_has_primary_capture_reflects_captures(self):
        self.assertFalse(self.version.has_primary_capture)
        self._make_capture(EvidenceCapture.Role.PRIMARY)
        self.assertTrue(EvidenceVersion.objects.get(pk=self.version.pk).has_primary_capture)


class EvidenceVersionUniquenessTests(TestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.student = make_student('versionstudent', self.department)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)
        self.evidence = Evidence.objects.create(participation=self.participation)

    def test_one_evidence_per_participation(self):
        with self.assertRaises(IntegrityError):
            Evidence.objects.create(participation=self.participation)

    def test_duplicate_version_number_rejected(self):
        EvidenceVersion.objects.create(evidence=self.evidence, version_number=1, submitted_by=self.student)
        with self.assertRaises(IntegrityError):
            EvidenceVersion.objects.create(evidence=self.evidence, version_number=1, submitted_by=self.student)

    def test_second_version_number_allowed(self):
        EvidenceVersion.objects.create(evidence=self.evidence, version_number=1, submitted_by=self.student)
        v2 = EvidenceVersion.objects.create(evidence=self.evidence, version_number=2, submitted_by=self.student)
        self.assertEqual(self.evidence.versions.count(), 2)
        self.assertEqual(v2.version_number, 2)


class EffectiveVerificationTests(TestCase):
    def setUp(self):
        self.college = make_college()
        self.department = make_department('CS', 'Computer Science')
        self.event_coordinator = make_event_coordinator('hodcs', self.department)
        self.faculty = make_faculty('facultycs2', self.department)
        self.student = make_student('effectivestudent', self.department)
        self.event = make_todays_published_event(
            created_by=self.event_coordinator, college=self.college, department=self.department,
        )
        self.participation = make_participation(student=self.student, event=self.event)
        self.evidence = Evidence.objects.create(participation=self.participation)
        self.version = EvidenceVersion.objects.create(evidence=self.evidence, version_number=1,
                                                      submitted_by=self.student)

    def test_no_verification_means_no_effective_decision(self):
        self.assertIsNone(self.version.effective_verification)

    def test_faculty_decision_is_effective_without_override(self):
        EvidenceVerification.objects.create(
            evidence_version=self.version, reviewer=self.faculty, decision=EvidenceVerification.Decision.VERIFIED,
        )
        self.assertEqual(self.version.effective_verification.decision, EvidenceVerification.Decision.VERIFIED)

    def test_event_coordinator_override_takes_precedence_but_faculty_decision_is_preserved(self):
        faculty_decision = EvidenceVerification.objects.create(
            evidence_version=self.version, reviewer=self.faculty,
            decision=EvidenceVerification.Decision.REJECTED, reason='blurry',
        )
        EvidenceVerification.objects.create(
            evidence_version=self.version, reviewer=self.event_coordinator, is_event_coordinator_override=True,
            decision=EvidenceVerification.Decision.VERIFIED, reason='confirmed valid on review',
        )
        self.assertEqual(self.version.effective_verification.decision, EvidenceVerification.Decision.VERIFIED)
        # The original Faculty row is untouched, not deleted or mutated.
        faculty_decision.refresh_from_db()
        self.assertEqual(faculty_decision.decision, EvidenceVerification.Decision.REJECTED)
        self.assertEqual(self.version.verifications.count(), 2)
