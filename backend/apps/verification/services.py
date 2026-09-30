"""
Business-logic layer for the Evidence/EvidenceVersion/EvidenceVerification
state machine. Views never mutate these models directly — every state
transition goes through a function here, each wrapped in `transaction.atomic`
with a row lock on the parent `Evidence` so two concurrent requests (two
resubmission attempts, two Faculty decisions) can never both win a race
(e.g. both creating "version 2", or both recording a decision that leaves
the evidence in an inconsistent status).
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.notifications import services as notifications
from apps.participation.eligibility import assert_capture_window_open
from apps.participation.geocoding import reverse_geocode
from apps.participation.models import Participation
from apps.participation.validation import (
    compute_venue_distance,
    validate_and_identify_image,
    validate_device_timestamp_for_event,
    validate_gps,
)

from .models import Evidence, EvidenceCapture, EvidenceVerification, EvidenceVersion


def _lock_or_create_evidence(participation: Participation) -> Evidence:
    evidence, _created = Evidence.objects.get_or_create(participation=participation)
    return Evidence.objects.select_for_update().get(pk=evidence.pk)


@transaction.atomic
def open_evidence_version(*, participation: Participation, user) -> EvidenceVersion:
    """
    Opens (or idempotently re-fetches) the current in-progress
    EvidenceVersion for a participation. A new version is only ever created
    when there is no existing version yet (this is "version 1"), or the
    latest version has already been submitted AND its effective decision is
    RESUBMISSION_REQUIRED — this is the sole mechanism by which a
    resubmission comes into being, and it is safe under concurrency because
    the parent Evidence row is locked for the duration of the transaction.
    """
    if participation.student_id != user.id:
        raise serializers.ValidationError('Only the participating student may submit evidence.')

    # The window is the event date and nothing else. Checked before any row is
    # created so a closed window cannot leave an empty version behind.
    assert_capture_window_open(participation.event)

    evidence = _lock_or_create_evidence(participation)
    latest_version = evidence.versions.order_by('-version_number').first()

    if latest_version is not None and latest_version.submitted_at is None:
        # Still capturing for this version — idempotent reopen.
        return latest_version

    if latest_version is not None:
        effective = latest_version.effective_verification
        if effective is None or effective.decision != EvidenceVerification.Decision.RESUBMISSION_REQUIRED:
            raise serializers.ValidationError(
                'A new evidence version can only be started after Faculty requests resubmission.',
            )

    next_version_number = (latest_version.version_number + 1) if latest_version else 1
    submission_reason = ''
    if latest_version is not None:
        effective = latest_version.effective_verification
        submission_reason = effective.reason if effective else ''

    version = EvidenceVersion.objects.create(
        evidence=evidence,
        version_number=next_version_number,
        submitted_by=user,
        submission_reason=submission_reason,
    )
    action = 'EVIDENCE_CREATED' if next_version_number == 1 else 'EVIDENCE_VERSION_CREATED'
    AuditLog.record(
        actor=user, action=action,
        description=f'Evidence version {next_version_number} opened for evidence #{evidence.id}.',
    )
    return version


@transaction.atomic
def add_capture_to_version(*, version: EvidenceVersion, user, capture_role, image, device_capture_timestamp,
                           latitude, longitude, gps_accuracy) -> EvidenceCapture:
    if version.evidence.participation.student_id != user.id:
        raise serializers.ValidationError('Only the participating student may upload evidence captures.')
    if version.submitted_at is not None:
        raise serializers.ValidationError('This evidence version has already been submitted.')
    if capture_role == EvidenceCapture.Role.PRIMARY and version.has_primary_capture:
        raise serializers.ValidationError('A primary capture has already been uploaded for this version.')

    event = version.evidence.participation.event
    validate_gps(latitude=latitude, longitude=longitude, accuracy=gps_accuracy)
    validate_device_timestamp_for_event(device_capture_timestamp, event.event_date)
    mime_type, file_size, sha256_hash = validate_and_identify_image(image)
    venue_distance, location_warning = compute_venue_distance(event, latitude=latitude, longitude=longitude)

    return EvidenceCapture.objects.create(
        evidence_version=version,
        capture_role=capture_role,
        object_reference=image,
        mime_type=mime_type,
        file_size=file_size,
        sha256_hash=sha256_hash,
        device_capture_timestamp=device_capture_timestamp,
        latitude=latitude,
        longitude=longitude,
        gps_accuracy=gps_accuracy,
        venue_distance=venue_distance,
        location_warning=location_warning,
        **_resolved_address_fields(latitude, longitude, gps_accuracy),
    )


def _resolved_address_fields(latitude, longitude, gps_accuracy):
    """Address fields for a new capture, or empty ones.

    Kept deliberately total: reverse_geocode already swallows its own
    failures, and this returns usable defaults either way, so a capture is
    never lost to a geocoding problem.
    """
    resolved = reverse_geocode(latitude, longitude, gps_accuracy=gps_accuracy)
    if resolved is None:
        return {}
    return {
        'resolved_address': resolved.address,
        'address_precision': resolved.precision,
        'address_provider': resolved.provider,
        'address_resolved_at': timezone.now(),
    }


@transaction.atomic
def submit_version(*, version: EvidenceVersion, user) -> EvidenceVersion:
    if version.evidence.participation.student_id != user.id:
        raise serializers.ValidationError('Only the participating student may submit this evidence version.')

    evidence = Evidence.objects.select_for_update().get(pk=version.evidence_id)
    version.refresh_from_db()
    if version.submitted_at is not None:
        # Idempotent: a duplicate submit (double-click, offline-queue retry) returns the existing state.
        return version

    # Checked again here, not only when the version was opened: a session
    # opened minutes before midnight must not be submittable the next day.
    # An already-submitted version returns above, so a late duplicate retry of
    # a successful submission is still answered idempotently rather than
    # failing.
    assert_capture_window_open(version.evidence.participation.event)

    if not version.has_primary_capture:
        raise serializers.ValidationError('A primary capture is required before submitting.')

    version.submitted_at = timezone.now()
    version.save(update_fields=['submitted_at'])

    evidence.current_version = version
    evidence.status = Evidence.Status.SUBMITTED
    evidence.save(update_fields=['current_version', 'status', 'updated_at'])

    participation = version.evidence.participation
    if participation.status != Participation.Status.SUBMITTED:
        participation.status = Participation.Status.SUBMITTED
        participation.submitted_at = timezone.now()
        participation.save(update_fields=['status', 'submitted_at', 'updated_at'])

    AuditLog.record(
        actor=user, action='EVIDENCE_SUBMITTED',
        description=f'Evidence version {version.version_number} submitted for evidence #{evidence.id}.',
    )
    return version


@transaction.atomic
def record_faculty_decision(*, evidence: Evidence, reviewer, decision, reason) -> EvidenceVerification:
    if decision != EvidenceVerification.Decision.VERIFIED and not reason.strip():
        raise serializers.ValidationError('A reason is required for this decision.')

    evidence = Evidence.objects.select_for_update().get(pk=evidence.pk)
    version = evidence.current_version
    if version is None or version.submitted_at is None:
        raise serializers.ValidationError('This evidence has no submitted version to review.')
    if evidence.status not in (Evidence.Status.SUBMITTED, Evidence.Status.UNDER_REVIEW):
        raise serializers.ValidationError('This evidence version has already been decided.')

    verification = EvidenceVerification.objects.create(
        evidence_version=version, reviewer=reviewer, decision=decision, reason=reason,
        is_event_coordinator_override=False,
    )
    evidence.status = decision
    evidence.save(update_fields=['status', 'updated_at'])

    action_map = {
        EvidenceVerification.Decision.VERIFIED: 'EVIDENCE_VERIFIED',
        EvidenceVerification.Decision.REJECTED: 'EVIDENCE_REJECTED',
        EvidenceVerification.Decision.RESUBMISSION_REQUIRED: 'EVIDENCE_RESUBMISSION_REQUESTED',
    }
    AuditLog.record(
        actor=reviewer, action=action_map[decision],
        description=f'Faculty recorded {decision} for evidence #{evidence.id} version {version.version_number}.',
    )
    notifications.schedule(
        notifications.notify_evidence_decision,
        evidence=evidence, decision=decision, reason=reason, is_override=False, reviewer=reviewer,
    )
    return verification


@transaction.atomic
def mark_under_review(*, evidence: Evidence, viewer) -> None:
    """Best-effort SUBMITTED -> UNDER_REVIEW transition, triggered the first
    time a Faculty member opens the evidence detail. Not itself a decision,
    so it is not logged as one — kept quiet per the project's "don't log
    noisy view events" guidance."""
    if evidence.status != Evidence.Status.SUBMITTED:
        return
    Evidence.objects.filter(pk=evidence.pk, status=Evidence.Status.SUBMITTED).update(
        status=Evidence.Status.UNDER_REVIEW, updated_at=timezone.now(),
    )


@transaction.atomic
def record_event_coordinator_override(
    *, evidence: Evidence, event_coordinator, decision, reason,
) -> EvidenceVerification:
    if not reason.strip():
        raise serializers.ValidationError('A reason is required for an Event Coordinator override.')

    evidence = Evidence.objects.select_for_update().get(pk=evidence.pk)
    version = evidence.current_version
    if version is None or version.submitted_at is None:
        raise serializers.ValidationError('This evidence has no submitted version to override.')
    if not version.verifications.filter(is_event_coordinator_override=False).exists():
        raise serializers.ValidationError('This evidence version has no Faculty decision to override yet.')

    verification = EvidenceVerification.objects.create(
        evidence_version=version, reviewer=event_coordinator, decision=decision, reason=reason,
        is_event_coordinator_override=True,
    )
    # The Faculty decision row is left completely untouched — this only
    # changes the denormalized "effective" status shortcut used by list views.
    evidence.status = decision
    evidence.save(update_fields=['status', 'updated_at'])

    AuditLog.record(
        actor=event_coordinator,
        action='EVENT_COORDINATOR_VERIFICATION_OVERRIDE',
        description=(
            f'Event Coordinator override {decision} for evidence #{evidence.id} '
            f'version {version.version_number}.'
        ),
    )
    notifications.schedule(
        notifications.notify_evidence_decision,
        evidence=evidence, decision=decision, reason=reason, is_override=True, reviewer=event_coordinator,
    )
    return verification


def get_effective_decision(participation: Participation) -> str | None:
    """
    The single authoritative answer to "what is this participation's
    verification outcome?" — the effective decision on its evidence's
    *current* (latest submitted) version, where an Event Coordinator override always
    takes precedence over the Faculty decision it overrode
    (EvidenceVersion.effective_verification), without either row ever being
    mutated.

    Returns None when there is nothing decided yet: no evidence at all, an
    evidence whose current version was never submitted, or a submitted
    version Faculty has not ruled on.

    Downstream phases (attendance, OD, achievements) must call this rather
    than reading `Evidence.status` directly. `Evidence.status` is a
    denormalized shortcut maintained for list-view filtering, while this is
    computed from the append-only decision history that is the real source
    of truth.
    """
    evidence = getattr(participation, 'evidence', None)
    if evidence is None:
        return None
    version = evidence.current_version
    if version is None or version.submitted_at is None:
        return None
    effective = version.effective_verification
    return effective.decision if effective else None


def is_participation_verified(participation: Participation) -> bool:
    """True only when the effective decision (Faculty decision as possibly
    overridden by an Event Coordinator) is VERIFIED. A Faculty REJECTED that an Event Coordinator
    overrode to VERIFIED counts as verified; a Faculty VERIFIED that an Event Coordinator
    overrode to REJECTED does not."""
    return get_effective_decision(participation) == EvidenceVerification.Decision.VERIFIED
