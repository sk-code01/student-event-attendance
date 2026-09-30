"""
Two distinct eligibility checks, deliberately different:

`check_participation_eligibility` is the UX-facing check (is today the
event date?) used by the read-only GET /participations/eligibility/
endpoint to decide whether to even show the "Mark Participation" button
while the student is online.

`get_registration_for_new_participation` is used when actually opening a
Participation (POST /participations/). It does NOT gate on "today", because
a legitimately delayed offline sync — captured on the correct day, synced
later — must still be accepted. The authoritative "was this captured on the
event date" check happens per-capture, against that capture's own
device_capture_timestamp (see validation.py), not against the date the
HTTP request happens to arrive.
"""

from django.utils import timezone
from rest_framework import serializers

from apps.events.models import Event
from apps.registrations.models import Registration


def check_participation_eligibility(user, event: Event):
    """Returns (eligible: bool, reason: str | None).

    A DRAFT Participation (opened, but never actually submitted — e.g. its
    only capture attempt was rejected for bad GPS accuracy or a bad image)
    must NOT count as "already submitted": the student needs to be able to
    retry. Only a genuinely SUBMITTED/PENDING_VERIFICATION participation
    blocks a further attempt, matching the DB's OneToOneField, which this
    mirrors at the UX layer without contradicting it (submitCaptureSession's
    "open" step is idempotent and reuses the same DRAFT row on retry).
    """
    if event.status == Event.Status.CANCELLED:
        return False, 'This event has been cancelled.'
    if event.status == Event.Status.DRAFT:
        return False, 'This event is not open yet.'

    registration = Registration.objects.filter(student=user, event=event).first()
    if registration is None:
        return False, 'You are not registered for this event.'
    if registration.status != Registration.Status.REGISTERED:
        return False, 'Your registration for this event is not active.'

    participation = getattr(registration, 'participation', None)
    if participation is not None and participation.status != participation.Status.DRAFT:
        return False, 'You have already submitted participation for this event.'

    today = timezone.localdate()
    if event.event_date != today:
        return False, 'Participation is only available on the event date.'

    return True, None


def is_capture_window_open(event: Event) -> bool:
    """The live-capture window is exactly the event date — no earlier, and
    permanently closed once that date has passed."""
    return timezone.localdate() == event.event_date


def capture_window_closed_reason(event: Event) -> str | None:
    """The reason the window is shut, or None while it is open."""
    today = timezone.localdate()
    if today < event.event_date:
        return 'Live capture opens on the event date.'
    if today > event.event_date:
        return 'The live capture window closed when the event date ended.'
    return None


def assert_capture_window_open(event: Event) -> None:
    """Raises if the window is shut.

    Applied when a version is opened and again when it is submitted, so that
    a session opened on the event date cannot be submitted after midnight.
    The window closing is final: it is not reopened by a Faculty rejection,
    which is what makes "resubmit only while the event date is active" hold.
    """
    reason = capture_window_closed_reason(event)
    if reason is not None:
        raise serializers.ValidationError(reason)


def get_registration_for_new_participation(user, event: Event) -> Registration:
    """Raises serializers.ValidationError on any ineligibility. Returns the
    student's Registration on success. See module docstring for why this
    intentionally omits the "is today the event date" check."""
    if event.status == Event.Status.CANCELLED:
        raise serializers.ValidationError('This event has been cancelled.')
    if event.status == Event.Status.DRAFT:
        raise serializers.ValidationError('This event is not open yet.')

    try:
        registration = Registration.objects.get(student=user, event=event)
    except Registration.DoesNotExist:
        raise serializers.ValidationError('You are not registered for this event.')

    if registration.status != Registration.Status.REGISTERED:
        raise serializers.ValidationError('Your registration for this event is not active.')

    return registration
