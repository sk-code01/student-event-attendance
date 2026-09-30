"""
Business-logic layer for the achievement creation/approval state machine.

Two rules shape this module:
  * A verified participation never creates an achievement on its own — every
    row here exists because an authorized user explicitly created it.
  * An Event Coordinator/Admin is the approving authority, so a record they create is
    already authoritative; routing it through their own approval queue would
    be an approval loop. Faculty-created records go to PENDING_APPROVAL.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.notifications import services as notifications
from apps.participation.models import Participation
from apps.verification.services import get_effective_decision, is_participation_verified

from .models import Achievement

EDITABLE_FIELDS = ('title', 'description', 'achievement_type', 'achievement_date')


def assert_participation_is_verified(participation: Participation) -> None:
    if not is_participation_verified(participation):
        decision = get_effective_decision(participation) or 'not yet verified'
        raise serializers.ValidationError(
            f'An achievement can only be recorded against a participation whose evidence is verified '
            f'(current effective decision: {decision}).',
        )


def validate_achievement_date(*, achievement_date, participation: Participation) -> None:
    """The achievement cannot predate the event it came from, and cannot be
    dated in the future. Both are cheap sanity rules against obviously
    impossible records; nothing stricter is imposed because a result can
    legitimately be announced days or weeks after the event itself."""
    event_date = participation.event.event_date
    if achievement_date < event_date:
        raise serializers.ValidationError(
            {'achievement_date': f'Achievement date cannot be earlier than the event date ({event_date}).'},
        )
    if achievement_date > timezone.localdate():
        raise serializers.ValidationError({'achievement_date': 'Achievement date cannot be in the future.'})


@transaction.atomic
def create_achievement(*, participation: Participation, creator, submit_for_approval: bool, **fields) -> Achievement:
    assert_participation_is_verified(participation)
    validate_achievement_date(achievement_date=fields['achievement_date'], participation=participation)

    is_authority = creator.is_superuser or creator.role in (creator.Role.EVENT_COORDINATOR, creator.Role.ADMIN)
    if is_authority:
        status = Achievement.Status.APPROVED
        reviewed_by, reviewed_at = creator, timezone.now()
    else:
        status = Achievement.Status.PENDING_APPROVAL if submit_for_approval else Achievement.Status.DRAFT
        reviewed_by, reviewed_at = None, None

    achievement = Achievement.objects.create(
        participation=participation, created_by=creator, status=status,
        reviewed_by=reviewed_by, reviewed_at=reviewed_at, **fields,
    )
    AuditLog.record(
        actor=creator, action='ACHIEVEMENT_CREATED',
        description=f'Achievement #{achievement.id} "{achievement.title}" created with status {status} '
                    f'for participation #{participation.id}.',
    )
    if achievement.status == Achievement.Status.PENDING_APPROVAL:
        notifications.schedule(notifications.notify_achievement_pending, achievement=achievement)
    return achievement


@transaction.atomic
def update_achievement(*, achievement: Achievement, user, **fields) -> Achievement:
    """Editing is deliberately conservative: only the creator, and only while
    the record is still a DRAFT. Once it is queued for approval the reviewer
    must not be shown a moving target, and an APPROVED record is an official
    academic record that is never casually editable — a correction there
    needs its own authorized workflow, which this phase does not invent."""
    achievement = Achievement.objects.select_for_update().get(pk=achievement.pk)
    if achievement.status != Achievement.Status.DRAFT:
        raise serializers.ValidationError(
            f'Only a draft achievement can be edited (this one is {achievement.status.lower()}).',
        )
    if achievement.created_by_id != user.id:
        raise serializers.ValidationError('Only the creator can edit this draft.')

    if 'achievement_date' in fields:
        validate_achievement_date(
            achievement_date=fields['achievement_date'], participation=achievement.participation,
        )
    for field, value in fields.items():
        setattr(achievement, field, value)
    achievement.save(update_fields=[*fields.keys(), 'updated_at'])

    AuditLog.record(
        actor=user, action='ACHIEVEMENT_UPDATED',
        description=f'Achievement #{achievement.id} draft updated.',
    )
    return achievement


@transaction.atomic
def submit_achievement(*, achievement: Achievement, user) -> Achievement:
    achievement = Achievement.objects.select_for_update().get(pk=achievement.pk)
    if achievement.status != Achievement.Status.DRAFT:
        raise serializers.ValidationError(
            f'Only a draft achievement can be submitted for approval (this one is {achievement.status.lower()}).',
        )
    if achievement.created_by_id != user.id:
        raise serializers.ValidationError('Only the creator can submit this draft for approval.')

    achievement.status = Achievement.Status.PENDING_APPROVAL
    achievement.save(update_fields=['status', 'updated_at'])
    AuditLog.record(
        actor=user, action='ACHIEVEMENT_SUBMITTED',
        description=f'Achievement #{achievement.id} submitted for Event Coordinator approval.',
    )
    notifications.schedule(notifications.notify_achievement_pending, achievement=achievement)
    return achievement


@transaction.atomic
def approve_achievement(*, achievement: Achievement, reviewer) -> Achievement:
    achievement = _lock_pending(achievement)
    assert_participation_is_verified(achievement.participation)

    achievement.status = Achievement.Status.APPROVED
    achievement.reviewed_by = reviewer
    achievement.reviewed_at = timezone.now()
    achievement.rejection_reason = ''
    achievement.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action='ACHIEVEMENT_APPROVED',
        description=f'Achievement #{achievement.id} approved and is now official.',
    )
    notifications.schedule(notifications.notify_achievement_decision, achievement=achievement)
    return achievement


@transaction.atomic
def reject_achievement(*, achievement: Achievement, reviewer, reason: str) -> Achievement:
    if not reason.strip():
        raise serializers.ValidationError('A reason is required to reject an achievement.')
    achievement = _lock_pending(achievement)

    achievement.status = Achievement.Status.REJECTED
    achievement.reviewed_by = reviewer
    achievement.reviewed_at = timezone.now()
    achievement.rejection_reason = reason.strip()
    achievement.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action='ACHIEVEMENT_REJECTED',
        description=f'Achievement #{achievement.id} rejected.',
    )
    notifications.schedule(notifications.notify_achievement_decision, achievement=achievement)
    return achievement


def _lock_pending(achievement: Achievement) -> Achievement:
    achievement = Achievement.objects.select_for_update().select_related(
        'participation__event', 'participation__student',
    ).get(pk=achievement.pk)
    if achievement.status != Achievement.Status.PENDING_APPROVAL:
        raise serializers.ValidationError(
            f'Only an achievement pending approval can be decided (this one is {achievement.status.lower()}).',
        )
    return achievement
