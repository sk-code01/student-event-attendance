from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.participation.models import Participation
from apps.participation.tests.helpers import (
    iso, make_admin, make_college, make_department, make_event, make_faculty, make_fake_image_bytes,
    make_event_coordinator,
    make_registration, make_student, make_todays_published_event, make_uploaded_image,
)
from apps.verification.models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion

__all__ = [
    'iso', 'make_admin', 'make_college', 'make_department', 'make_event', 'make_faculty', 'make_fake_image_bytes',
    'make_event_coordinator', 'make_registration', 'make_student', 'make_todays_published_event', 'make_uploaded_image',
    'noon_on', 'make_participation', 'make_submitted_evidence', 'make_decided_participation',
    'make_verified_participation',
]


def noon_on(event_date):
    """A device_capture_timestamp anchored to `event_date`, safe against the
    "capture timestamp is in the future" rejection regardless of what time
    of day the test suite happens to run. A hardcoded noon is in the future
    whenever tests run before noon local time on `event_date` itself (e.g.
    a suite run at 00:30 AM would see "noon today" as ~11.5 hours ahead) —
    so when `event_date` is today, anchor to "a few seconds ago" instead;
    only fall back to a fixed noon for non-today dates (past/future-day
    rejection tests), where the exact time of day doesn't matter."""
    now = timezone.now()
    if timezone.localtime(now).date() == event_date:
        return now - timedelta(seconds=5)
    return timezone.make_aware(datetime.combine(event_date, time(12, 0)))


def make_participation(*, student, event):
    registration = make_registration(student=student, event=event)
    return Participation.objects.create(registration=registration)


def make_submitted_evidence(*, participation, submitted_by=None, version_number=1):
    """Directly builds a SUBMITTED Evidence + primary capture, bypassing the
    API, for tests whose focus is downstream (Faculty decision / Event Coordinator
    override) rather than the capture-upload flow itself."""
    submitted_by = submitted_by or participation.student
    evidence, _ = Evidence.objects.get_or_create(participation=participation)
    version = EvidenceVersion.objects.create(
        evidence=evidence, version_number=version_number, submitted_by=submitted_by,
        submitted_at=timezone.now(),
    )
    EvidenceCapture.objects.create(
        evidence_version=version, capture_role=EvidenceCapture.Role.PRIMARY,
        object_reference=make_uploaded_image(), mime_type='image/jpeg', file_size=100, sha256_hash='a' * 64,
        device_capture_timestamp=noon_on(participation.event.event_date), latitude=1, longitude=1, gps_accuracy=10,
    )
    evidence.current_version = version
    evidence.status = Evidence.Status.SUBMITTED
    evidence.save(update_fields=['current_version', 'status'])
    participation.status = Participation.Status.SUBMITTED
    participation.submitted_at = timezone.now()
    participation.save(update_fields=['status', 'submitted_at'])
    return evidence, version


def make_decided_participation(*, student, event, reviewer, decision, reason='because',
                               override_by=None, override_decision=None, override_reason='override reason'):
    """Builds a participation with submitted evidence and a recorded Faculty
    decision, optionally followed by an Event Coordinator override — the fixture downstream
    phases (attendance, OD, achievements) need in order to exercise every
    branch of the *effective* decision, including the two that matter most:
    Faculty REJECTED + Event Coordinator override VERIFIED (eligible) and Faculty VERIFIED +
    Event Coordinator override REJECTED (not eligible).

    It writes the verification rows directly rather than through the API
    because the focus of those tests is the downstream workflow, not the
    Phase 4 decision endpoints, which have their own coverage.
    """
    participation = make_participation(student=student, event=event)
    evidence, version = make_submitted_evidence(participation=participation)
    EvidenceVerification.objects.create(
        evidence_version=version, reviewer=reviewer, decision=decision, reason=reason,
        is_event_coordinator_override=False,
    )
    effective = decision
    if override_by is not None:
        EvidenceVerification.objects.create(
            evidence_version=version, reviewer=override_by, decision=override_decision,
            reason=override_reason, is_event_coordinator_override=True,
        )
        effective = override_decision
    Evidence.objects.filter(pk=evidence.pk).update(status=effective)
    evidence.refresh_from_db()
    return participation


def make_verified_participation(*, student, event, reviewer):
    """The happy-path fixture: a participation whose effective evidence
    decision is VERIFIED via a plain Faculty decision."""
    return make_decided_participation(
        student=student, event=event, reviewer=reviewer,
        decision=EvidenceVerification.Decision.VERIFIED, reason='looks good',
    )
