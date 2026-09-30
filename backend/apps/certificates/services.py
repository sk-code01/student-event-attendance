"""
Every certificate state transition, in one place.

Views never mutate Certificate rows directly. Each function here is wrapped
in `transaction.atomic` and takes a row lock on the participation's existing
certificates where a race would otherwise matter — two submissions arriving
together must not both become "attempt 3".

The rules this module owns:

* the upload window opens at midnight after the event date, never on the day
  itself, and stays open until a certificate stands;
* a certificate can only be submitted when the student actually performed a
  live capture for that event;
* three attempts in total, after which only the Event Coordinator can accept
  the rejected certificate that already exists.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.audit.models import AuditLog
from apps.notifications import services as notifications
from apps.participation.models import Participation
from apps.participation.validation import validate_certificate_file

from .models import MAX_CERTIFICATE_ATTEMPTS, Certificate, FinalDecision


# --------------------------------------------------------------- upload window

def certificate_window_opens_on(event):
    """The first date a certificate may be uploaded: the day after the event.

    Stated as a date rather than a timestamp because the rule is "00:00 of the
    next calendar day", which is exactly "the next date" in the project's
    local timezone.
    """
    from datetime import timedelta
    return event.event_date + timedelta(days=1)


def certificate_window_closed_reason(participation) -> str | None:
    """Why the student cannot upload right now, or None when they can.

    Ordered so the message names the first thing that actually blocks them,
    rather than a later rule they have not reached yet.
    """
    event = participation.event
    today = timezone.localdate()

    if today < certificate_window_opens_on(event):
        return (
            'Certificate upload opens at midnight after the event date '
            f'({certificate_window_opens_on(event):%d %b %Y}).'
        )

    if not has_valid_live_capture(participation):
        return 'A certificate can only be uploaded for an event you submitted a live capture for.'

    certificates = list(participation.certificates.all())
    if any(certificate.is_accepted for certificate in certificates):
        return 'A certificate has already been accepted for this event.'
    if any(certificate.status == Certificate.Status.SUBMITTED for certificate in certificates):
        return 'Your certificate is waiting for Faculty verification.'
    if len(certificates) >= MAX_CERTIFICATE_ATTEMPTS:
        return (
            f'All {MAX_CERTIFICATE_ATTEMPTS} certificate attempts have been used. '
            'Your Event Coordinator can accept the certificate you already submitted.'
        )
    return None


def has_valid_live_capture(participation) -> bool:
    """True when the student actually submitted live-capture evidence that has
    not been rejected.

    A certificate must never be a way around the live-capture requirement, so
    "registered" is not enough — the participation has to have been submitted.
    Evidence that is still awaiting a Faculty decision counts: making students
    wait for verification before they may upload would shut them out of the
    window through no fault of their own.
    """
    if participation.status != Participation.Status.SUBMITTED:
        return False

    evidence = getattr(participation, 'evidence', None)
    if evidence is None:
        return False

    from apps.verification.models import Evidence
    return evidence.status != Evidence.Status.REJECTED


def attempts_used(participation) -> int:
    return participation.certificates.count()


def attempts_remaining(participation) -> int:
    return max(0, MAX_CERTIFICATE_ATTEMPTS - attempts_used(participation))


# ------------------------------------------------------------------ submission

@transaction.atomic
def submit_certificate(*, participation, user, uploaded_file):
    """Records a new certificate attempt for `participation`."""
    if participation.student_id != user.id:
        raise serializers.ValidationError('Only the participating student may submit a certificate.')

    # Lock the existing attempts so a second request cannot read the same
    # count and insert a duplicate attempt number.
    locked = list(
        Certificate.objects.select_for_update()
        .filter(participation=participation)
        .order_by('attempt_number'),
    )

    reason = certificate_window_closed_reason(participation)
    if reason is not None:
        raise serializers.ValidationError(reason)

    mime_type, file_size, sha256_hash = validate_certificate_file(uploaded_file)

    attempt_number = len(locked) + 1
    if attempt_number > MAX_CERTIFICATE_ATTEMPTS:
        raise serializers.ValidationError(
            f'All {MAX_CERTIFICATE_ATTEMPTS} certificate attempts have been used.',
        )

    certificate = Certificate(
        participation=participation,
        attempt_number=attempt_number,
        mime_type=mime_type,
        file_size=file_size,
        sha256_hash=sha256_hash,
        original_filename=(getattr(uploaded_file, 'name', '') or '')[:255],
        submitted_by=user,
        status=Certificate.Status.SUBMITTED,
    )
    certificate.object_reference.save(
        getattr(uploaded_file, 'name', 'certificate'), uploaded_file, save=False,
    )
    certificate.save()

    AuditLog.record(
        actor=user, action='CERTIFICATE_SUBMITTED',
        description=(
            f'Certificate attempt {attempt_number} submitted for participation '
            f'#{participation.id} (event "{participation.event.title}").'
        ),
    )
    notifications.schedule(notifications.notify_certificate_submitted, certificate=certificate)
    return certificate


# ------------------------------------------------------------------- decisions

@transaction.atomic
def record_faculty_decision(*, certificate, reviewer, decision, reason=''):
    """Faculty verifies or rejects a submitted certificate."""
    certificate = Certificate.objects.select_for_update().get(pk=certificate.pk)

    if certificate.status != Certificate.Status.SUBMITTED:
        raise serializers.ValidationError('This certificate has already been decided.')

    if decision not in (Certificate.Status.VERIFIED, Certificate.Status.REJECTED):
        raise serializers.ValidationError('A certificate decision is either VERIFIED or REJECTED.')

    reason = (reason or '').strip()
    if decision == Certificate.Status.REJECTED and not reason:
        # The student has to be told what to fix; a bare rejection is not
        # actionable, and the database refuses it too.
        raise serializers.ValidationError({'reason': 'A reason is required when rejecting a certificate.'})

    certificate.status = decision
    certificate.reviewed_by = reviewer
    certificate.reviewed_at = timezone.now()
    certificate.rejection_reason = reason if decision == Certificate.Status.REJECTED else ''
    certificate.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason', 'updated_at'])

    AuditLog.record(
        actor=reviewer, action=f'CERTIFICATE_{decision}',
        description=(
            f'Certificate attempt {certificate.attempt_number} for participation '
            f'#{certificate.participation_id} was {decision.lower()}.'
        ),
    )
    notifications.schedule(notifications.notify_certificate_decision, certificate=certificate)
    return certificate


@transaction.atomic
def record_final_decision(*, certificate, coordinator, decision, reason=''):
    """The Event Coordinator's final accept/reject on a verified certificate.

    Only a certificate Faculty have already verified reaches this point:
    requirement 23 places the coordinator *after* verification, not instead of
    it. A rejection here is final and deliberately opens no new resubmission
    path — the student's attempts are governed by the Faculty decisions alone,
    and inventing an extra attempt here would quietly raise the limit of three.
    """
    certificate = Certificate.objects.select_for_update().get(pk=certificate.pk)

    if certificate.status != Certificate.Status.VERIFIED:
        raise serializers.ValidationError(
            'Only a certificate that Faculty have verified can receive a final decision.',
        )
    if certificate.final_decision:
        raise serializers.ValidationError('A final decision has already been recorded.')
    if decision not in (FinalDecision.ACCEPTED, FinalDecision.REJECTED):
        raise serializers.ValidationError('A final decision is either ACCEPTED or REJECTED.')

    reason = (reason or '').strip()
    if decision == FinalDecision.REJECTED and not reason:
        raise serializers.ValidationError(
            {'reason': 'A reason is required when rejecting a certificate.'},
        )

    certificate.final_decision = decision
    certificate.final_decided_by = coordinator
    certificate.final_decided_at = timezone.now()
    certificate.final_rejection_reason = reason if decision == FinalDecision.REJECTED else ''
    certificate.save(update_fields=[
        'final_decision', 'final_decided_by', 'final_decided_at',
        'final_rejection_reason', 'updated_at',
    ])

    AuditLog.record(
        actor=coordinator, action=f'CERTIFICATE_FINAL_{decision}',
        description=(
            f'Event Coordinator recorded the final decision {decision} on certificate attempt '
            f'{certificate.attempt_number} for participation #{certificate.participation_id}.'
        ),
    )
    notifications.schedule(notifications.notify_certificate_final_decision, certificate=certificate)
    return certificate


@transaction.atomic
def accept_exhausted_certificate(*, certificate, coordinator):
    """The Event Coordinator accepts a rejected certificate once the student
    has no attempts left.

    Deliberately narrow: this is the release valve for a student who ran out
    of attempts, not a general override of Faculty. It is refused while the
    student can still resubmit, so it can never be used to shortcut the normal
    verification path.
    """
    certificate = Certificate.objects.select_for_update().get(pk=certificate.pk)
    participation = certificate.participation

    if certificate.status != Certificate.Status.REJECTED:
        raise serializers.ValidationError('Only a rejected certificate can be accepted this way.')
    if attempts_used(participation) < MAX_CERTIFICATE_ATTEMPTS:
        raise serializers.ValidationError(
            'The student still has certificate attempts remaining, so they can resubmit instead.',
        )
    if participation.certificates.filter(status=Certificate.Status.ACCEPTED_BY_COORDINATOR).exists():
        raise serializers.ValidationError('A certificate has already been accepted for this event.')

    certificate.status = Certificate.Status.ACCEPTED_BY_COORDINATOR
    certificate.reviewed_by = coordinator
    certificate.reviewed_at = timezone.now()
    certificate.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'updated_at'])

    # Recorded explicitly: this is a manual override of a Faculty rejection and
    # has to be attributable afterwards.
    AuditLog.record(
        actor=coordinator, action='CERTIFICATE_ACCEPTED_AFTER_ATTEMPTS_EXHAUSTED',
        description=(
            f'Event Coordinator accepted rejected certificate attempt {certificate.attempt_number} '
            f'for participation #{participation.id} (event "{participation.event.title}") '
            'after all attempts were used.'
        ),
    )
    notifications.schedule(notifications.notify_certificate_decision, certificate=certificate)
    return certificate


def effective_certificate(participation):
    """The certificate that currently counts for this participation, or None.

    An accepted one always wins; otherwise the most recent attempt is what the
    student and the reviewers are looking at.
    """
    certificates = sorted(participation.certificates.all(), key=lambda c: c.attempt_number)
    accepted = next((c for c in certificates if c.is_accepted), None)
    return accepted or (certificates[-1] if certificates else None)
