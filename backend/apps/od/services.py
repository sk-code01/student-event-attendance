"""
Business-logic layer for the OD request/approval state machine — structurally
parallel to `apps.attendance.services` but operating on a completely separate
record. Nothing here reads or writes attendance, and approving/rejecting OD
never touches an attendance record (or vice versa): the two are independent
academic decisions.

Concurrency, the effective-verification eligibility gate, and the
"a decision is final" rule work exactly as they do for attendance.
"""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.notifications import services as notifications
from apps.participation.models import Participation
from apps.verification.services import get_effective_decision, is_participation_verified

from .models import ODRequest


def assert_participation_is_verified(participation: Participation) -> None:
    if not is_participation_verified(participation):
        decision = get_effective_decision(participation) or 'not yet verified'
        raise serializers.ValidationError(
            f'OD can only be requested for a participation whose evidence is verified '
            f'(current effective decision: {decision}).',
        )


@transaction.atomic
def request_od(*, participation: Participation, requested_by, reason: str) -> ODRequest:
    if not reason.strip():
        raise serializers.ValidationError('A reason is required to request OD.')
    assert_participation_is_verified(participation)
    try:
        od_request = ODRequest.objects.create(
            participation=participation, requested_by=requested_by, reason=reason.strip(),
        )
    except IntegrityError:
        raise serializers.ValidationError('An OD request already exists for this participation.')

    AuditLog.record(
        actor=requested_by, action='OD_REQUESTED',
        description=f'OD requested for participation #{participation.id} (OD request #{od_request.id}).',
    )
    notifications.schedule(notifications.notify_od_request, od_request=od_request)
    return od_request


@transaction.atomic
def approve_od(*, od_request: ODRequest, reviewer) -> ODRequest:
    od_request = _lock_pending(od_request)
    assert_participation_is_verified(od_request.participation)

    od_request.status = ODRequest.Status.APPROVED
    od_request.reviewed_by = reviewer
    od_request.reviewed_at = timezone.now()
    od_request.rejection_reason = ''
    od_request.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action='OD_APPROVED',
        description=f'OD request #{od_request.id} approved for participation #{od_request.participation_id}.',
    )
    notifications.schedule(notifications.notify_od_decision, od_request=od_request)
    return od_request


@transaction.atomic
def reject_od(*, od_request: ODRequest, reviewer, reason: str) -> ODRequest:
    if not reason.strip():
        raise serializers.ValidationError('A reason is required to reject an OD request.')
    od_request = _lock_pending(od_request)

    od_request.status = ODRequest.Status.REJECTED
    od_request.reviewed_by = reviewer
    od_request.reviewed_at = timezone.now()
    od_request.rejection_reason = reason.strip()
    od_request.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action='OD_REJECTED',
        description=f'OD request #{od_request.id} rejected for participation #{od_request.participation_id}.',
    )
    notifications.schedule(notifications.notify_od_decision, od_request=od_request)
    return od_request


def _lock_pending(od_request: ODRequest) -> ODRequest:
    od_request = ODRequest.objects.select_for_update().select_related(
        'participation__event', 'participation__student',
    ).get(pk=od_request.pk)
    if od_request.status != ODRequest.Status.PENDING:
        raise serializers.ValidationError(
            f'This OD request has already been {od_request.status.lower()}.',
        )
    return od_request
