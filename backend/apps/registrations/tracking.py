"""
The department-wide tracking view: one row per registration, carrying that
student's position in every downstream stage of the workflow.

This exists because the question an Event Coordinator actually asks — "who
registered, who turned up, who has evidence, who has a certificate, who has
attendance?" — spans six apps, and answering it by calling six endpoints and
joining them in the browser would be both slow and inconsistent.

The derived statuses here are *computed*, never stored. Nothing in this module
writes, and no status it reports is treated as authoritative by any workflow:
`LIVE_CAPTURE_NOT_SUBMITTED` in particular is a read-time observation about a
student who has no participation after the event date, and never a substitute
for the Event Coordinator deciding attendance (requirement 15).
"""

from django.db.models import Prefetch
from django.utils import timezone

from apps.attendance.models import Attendance
from apps.certificates.models import MAX_CERTIFICATE_ATTEMPTS, Certificate
from apps.participation.models import Participation
from apps.verification.models import Evidence


class LiveCaptureStatus:
    NOT_SUBMITTED = 'NOT_SUBMITTED'
    AWAITING_EVENT = 'AWAITING_EVENT'
    OPEN_TODAY = 'OPEN_TODAY'
    IN_PROGRESS = 'IN_PROGRESS'
    SUBMITTED = 'SUBMITTED'


class CertificateStatus:
    NOT_ELIGIBLE = 'NOT_ELIGIBLE'
    WINDOW_NOT_OPEN = 'WINDOW_NOT_OPEN'
    NOT_SUBMITTED = 'NOT_SUBMITTED'
    SUBMITTED = 'SUBMITTED'
    VERIFIED = 'VERIFIED'
    REJECTED = 'REJECTED'
    ACCEPTED_BY_COORDINATOR = 'ACCEPTED_BY_COORDINATOR'


ATTENDANCE_NOT_RECORDED = 'NOT_RECORDED'
VERIFICATION_NOT_APPLICABLE = 'NOT_APPLICABLE'


def tracking_queryset(base):
    """Attaches everything a tracking row needs in a fixed number of queries.

    Without this the view would issue a handful of queries per registration,
    which is exactly the shape that looks fine on a demo department and falls
    over on a real one.
    """
    return base.select_related(
        'student', 'student__department', 'event', 'event__department',
    ).prefetch_related(
        Prefetch(
            'participation',
            queryset=Participation.objects.select_related('event').prefetch_related(
                Prefetch(
                    'evidence',
                    queryset=Evidence.objects.select_related('current_version').prefetch_related(
                        'current_version__captures',
                    ),
                ),
                Prefetch('certificates', queryset=Certificate.objects.order_by('attempt_number')),
            ),
        ),
        Prefetch('attendance', queryset=Attendance.objects.select_related('reviewed_by')),
    )


def _participation_of(registration):
    return getattr(registration, 'participation', None)


def live_capture_status(registration, *, today=None):
    """Where this student stands on the live capture.

    The distinction that matters is between "has not captured yet" and "can
    never capture now": once the event date has passed the window is shut for
    good, so a student with no submitted participation is reported as
    NOT_SUBMITTED — the state requirement 15 asks the coordinator to act on.
    """
    today = today or timezone.localdate()
    event_date = registration.event.event_date
    participation = _participation_of(registration)

    if participation is not None and participation.status == Participation.Status.SUBMITTED:
        return LiveCaptureStatus.SUBMITTED
    if today < event_date:
        return LiveCaptureStatus.AWAITING_EVENT
    if today == event_date:
        # Opened a session but never submitted it, versus never started.
        return (
            LiveCaptureStatus.IN_PROGRESS if participation is not None
            else LiveCaptureStatus.OPEN_TODAY
        )
    return LiveCaptureStatus.NOT_SUBMITTED


def verification_status(registration):
    """The evidence decision as it currently stands, including an Event
    Coordinator override where one exists."""
    participation = _participation_of(registration)
    if participation is None:
        return VERIFICATION_NOT_APPLICABLE
    evidence = getattr(participation, 'evidence', None)
    if evidence is None:
        return VERIFICATION_NOT_APPLICABLE
    return evidence.status


def certificate_state(registration, *, today=None):
    """The certificate position, as (status, attempts_used, attempts_remaining).

    Mirrors the rules the certificates app enforces rather than re-deciding
    them: no live capture means not eligible, and the window opens the day
    after the event.
    """
    today = today or timezone.localdate()
    participation = _participation_of(registration)

    if participation is None or participation.status != Participation.Status.SUBMITTED:
        return CertificateStatus.NOT_ELIGIBLE, 0, 0

    certificates = sorted(participation.certificates.all(), key=lambda c: c.attempt_number)
    used = len(certificates)
    remaining = max(0, MAX_CERTIFICATE_ATTEMPTS - used)

    accepted = next((c for c in certificates if c.is_accepted), None)
    if accepted is not None:
        return accepted.status, used, remaining
    if certificates:
        return certificates[-1].status, used, remaining
    if today <= registration.event.event_date:
        return CertificateStatus.WINDOW_NOT_OPEN, used, remaining
    return CertificateStatus.NOT_SUBMITTED, used, remaining


def attendance_status(registration):
    attendance = getattr(registration, 'attendance', None)
    return attendance.status if attendance is not None else ATTENDANCE_NOT_RECORDED


def capture_location(registration):
    """Where the student's primary capture was taken, as a reviewer should read
    it, or None when there is no capture.

    Requirement 13 asks for this in the coordinator's review as well as in
    Faculty verification, and it is the capture's own summary rather than a
    second rendering of the same data, so the two never disagree.
    """
    participation = _participation_of(registration)
    if participation is None:
        return None
    evidence = getattr(participation, 'evidence', None)
    if evidence is None or evidence.current_version_id is None:
        return None

    captures = list(evidence.current_version.captures.all())
    primary = next((c for c in captures if c.capture_role == 'PRIMARY'), None)
    return primary.location_summary if primary is not None else None


def build_row(registration, *, today=None):
    """One tracking row. Pure computation over already-fetched relations."""
    today = today or timezone.localdate()
    participation = _participation_of(registration)
    certificate_status, attempts_used, attempts_remaining = certificate_state(
        registration, today=today,
    )
    attendance = getattr(registration, 'attendance', None)
    student = registration.student
    event = registration.event

    return {
        'registration_id': registration.id,
        'student': {
            'id': student.id,
            'username': student.username,
            'full_name': student.full_name,
            'university_registration_number': student.university_registration_number,
            'department': student.department.name if student.department_id else None,
        },
        'event': {
            'id': event.id,
            'title': event.title,
            'event_date': event.event_date,
            'venue': event.venue,
            'status': event.status,
        },
        'registration_status': registration.status,
        'registered_at': registration.registered_at,

        'participation_id': participation.id if participation else None,
        'participation_status': participation.status if participation else None,
        'live_capture_status': live_capture_status(registration, today=today),
        'live_capture_submitted_at': participation.submitted_at if participation else None,
        'live_capture_location': capture_location(registration),

        'verification_status': verification_status(registration),

        'certificate_status': certificate_status,
        'certificate_attempts_used': attempts_used,
        'certificate_attempts_remaining': attempts_remaining,

        'attendance_status': attendance_status(registration),
        'attendance_is_manual': attendance.is_manual if attendance else False,
        'attendance_decided_by': (
            attendance.reviewed_by.username
            if attendance is not None and attendance.reviewed_by_id
            else None
        ),
    }


# --------------------------------------------------------------------- filters

FILTERABLE = {
    'registration_status': lambda row, value: row['registration_status'] == value,
    'participation_status': lambda row, value: row['participation_status'] == value,
    'live_capture_status': lambda row, value: row['live_capture_status'] == value,
    'verification_status': lambda row, value: row['verification_status'] == value,
    'certificate_status': lambda row, value: row['certificate_status'] == value,
    'attendance_status': lambda row, value: row['attendance_status'] == value,
}


def apply_row_filters(rows, params):
    """Filters on the derived statuses.

    These are computed rather than stored, so they cannot be pushed into SQL
    without denormalising six workflows into this table — which would then
    need keeping in step with every one of them. The database narrowing that
    *can* be expressed (department, event, student) happens in the queryset
    before this point, so what reaches here is already one department's rows.
    """
    for key, predicate in FILTERABLE.items():
        value = (params.get(key) or '').strip().upper()
        if value:
            rows = [row for row in rows if predicate(row, value)]
    return rows
