"""
Business-logic layer for the attendance request/approval state machine.
Views never mutate `Attendance` directly — every transition goes through a
function here, wrapped in `transaction.atomic` with a `select_for_update`
row lock, so two concurrent Event Coordinator decisions on the same request cannot both
win (the second observes the row is no longer PENDING and is rejected).

The eligibility gate is deliberately NOT a local re-implementation of
"is this verified": it calls
`apps.verification.services.is_participation_verified`, which resolves the
effective decision (Faculty decision as possibly overridden by an Event Coordinator) from
the append-only decision history rather than reading a denormalized status.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.notifications import services as notifications
from apps.participation.models import Participation
from apps.verification.services import get_effective_decision, is_participation_verified

from .models import Attendance


def assert_participation_is_verified(participation: Participation) -> None:
    """Shared eligibility gate. A registration, a participation with no
    evidence, unverified/rejected/resubmission-required evidence are all
    refused; only an effective VERIFIED decision passes."""
    if not is_participation_verified(participation):
        decision = get_effective_decision(participation) or 'not yet verified'
        raise serializers.ValidationError(
            f'Attendance can only be requested for a participation whose evidence is verified '
            f'(current effective decision: {decision}).',
        )


@transaction.atomic
def request_attendance(*, participation: Participation, requested_by) -> Attendance:
    assert_participation_is_verified(participation)
    try:
        attendance = Attendance.objects.create(
            participation=participation,
            # Derived, never client-supplied: the registration is whatever this
            # participation belongs to.
            registration_id=participation.registration_id,
            requested_by=requested_by,
        )
    except IntegrityError:
        # The OneToOne constraint is the real duplicate guard — a concurrent
        # second request loses here rather than creating a parallel record.
        raise serializers.ValidationError('An attendance record already exists for this participation.')

    AuditLog.record(
        actor=requested_by, action='ATTENDANCE_REQUESTED',
        description=f'Attendance requested for participation #{participation.id} (attendance #{attendance.id}).',
    )
    notifications.schedule(notifications.notify_attendance_request, attendance=attendance)
    return attendance


@transaction.atomic
def mark_attendance(*, registration, coordinator, status, reason='') -> Attendance:
    """The Event Coordinator records or changes attendance directly.

    This is the only path that does not require verified evidence, and that is
    deliberate: a student who never submitted a live capture has nothing to
    verify, and recording their attendance is exactly what requirement 15 asks
    for. Nothing here infers attendance — the coordinator states it, and the
    record names them as the person who did.

    Marking is idempotent in the sense that a second call updates the existing
    record rather than failing on the one-per-registration constraint; the
    previous state is kept in the audit trail.
    """
    if status not in (Attendance.Status.APPROVED, Attendance.Status.REJECTED):
        raise serializers.ValidationError('Attendance can be marked as APPROVED or REJECTED.')

    reason = (reason or '').strip()
    if status == Attendance.Status.REJECTED and not reason:
        raise serializers.ValidationError({'reason': 'A reason is required when rejecting attendance.'})

    attendance = (
        Attendance.objects.select_for_update()
        .filter(registration=registration)
        .first()
    )
    participation = getattr(registration, 'participation', None)
    previous_status = attendance.status if attendance else None

    if attendance is None:
        attendance = Attendance.objects.create(
            registration=registration,
            participation=participation,
            status=status,
            is_manual=True,
            requested_by=None,
            reviewed_by=coordinator,
            reviewed_at=timezone.now(),
            rejection_reason=reason if status == Attendance.Status.REJECTED else '',
        )
    else:
        attendance.status = status
        attendance.is_manual = True
        attendance.participation = participation
        attendance.reviewed_by = coordinator
        attendance.reviewed_at = timezone.now()
        attendance.rejection_reason = reason if status == Attendance.Status.REJECTED else ''
        attendance.save(update_fields=[
            'status', 'is_manual', 'participation', 'reviewed_by', 'reviewed_at',
            'rejection_reason', 'updated_at',
        ])

    AuditLog.record(
        actor=coordinator, action='ATTENDANCE_MARKED_MANUALLY',
        description=(
            f'Event Coordinator set attendance to {status} for registration #{registration.id} '
            f'(student {registration.student_id}, event "{registration.event.title}")'
            + (f', previously {previous_status}.' if previous_status else '.')
        ),
    )
    notifications.schedule(notifications.notify_attendance_decision, attendance=attendance)
    return attendance


@transaction.atomic
def approve_attendance(*, attendance: Attendance, reviewer) -> Attendance:
    attendance = _lock_pending(attendance)
    # Re-checked at decision time, not only at request time: an Event Coordinator override
    # could have flipped the effective decision away from VERIFIED after the
    # Faculty request was raised.
    assert_participation_is_verified(attendance.participation)

    attendance.status = Attendance.Status.APPROVED
    attendance.reviewed_by = reviewer
    attendance.reviewed_at = timezone.now()
    attendance.rejection_reason = ''
    attendance.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action='ATTENDANCE_APPROVED',
        description=f'Attendance #{attendance.id} approved for participation #{attendance.participation_id}.',
    )
    notifications.schedule(notifications.notify_attendance_decision, attendance=attendance)
    return attendance


@transaction.atomic
def reject_attendance(*, attendance: Attendance, reviewer, reason: str) -> Attendance:
    if not reason.strip():
        raise serializers.ValidationError('A reason is required to reject attendance.')
    attendance = _lock_pending(attendance)

    attendance.status = Attendance.Status.REJECTED
    attendance.reviewed_by = reviewer
    attendance.reviewed_at = timezone.now()
    attendance.rejection_reason = reason.strip()
    attendance.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action='ATTENDANCE_REJECTED',
        description=f'Attendance #{attendance.id} rejected for participation #{attendance.participation_id}.',
    )
    notifications.schedule(notifications.notify_attendance_decision, attendance=attendance)
    return attendance


def _lock_pending(attendance: Attendance) -> Attendance:
    """Row-locks the record and refuses anything that is not still PENDING —
    this is what makes APPROVED -> APPROVED (two racing reviewers) and
    REJECTED -> APPROVED (a stale browser tab) impossible. A decision is
    final; it is never silently overwritten."""
    # `of=('self',)` is required, not cosmetic: `participation` is nullable, so
    # select_related joins it as a LEFT OUTER JOIN and Postgres refuses
    # FOR UPDATE against the nullable side of an outer join. Locking only the
    # attendance row is also exactly the lock this needs.
    attendance = Attendance.objects.select_for_update(of=('self',)).select_related(
        'participation__event', 'participation__student',
        'registration__event', 'registration__student',
    ).get(pk=attendance.pk)
    if attendance.status != Attendance.Status.PENDING:
        raise serializers.ValidationError(
            f'This attendance request has already been {attendance.status.lower()}.',
        )
    return attendance
