"""
The one place notifications are created. Business services call the semantic
`notify_*` helpers at the bottom of this module; nothing else in the project
constructs a `Notification` directly, and no view does.

Two rules shape everything here:

**1. A notification must never break the business action it describes.**
Every helper is wrapped by `_safe`, which swallows and logs any exception, and
every call site schedules it with `transaction.on_commit(...)`. So the
notification is only attempted once the academic decision has actually
committed, and a failure to notify can no longer roll anything back — an Event Coordinator's
approval stands even if the notification insert fails. This is the deliberate
trade-off: we would rather lose a message than lose an approval.

**2. Recipients are derived, never supplied.** Every helper takes a business
object and works out who should hear about it. No client input reaches
`recipient`.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Notification

logger = logging.getLogger(__name__)


def _safe(fn):
    """Notification delivery is best-effort. A failure here is logged and
    dropped rather than propagated, because these helpers run after the
    business transaction has committed and must not turn a successful
    academic decision into a 500."""

    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001 - deliberately broad, see module docstring
            logger.exception('Notification delivery failed in %s', fn.__name__)
            return None

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


def _clean_route(route: str) -> str:
    """Only internal Angular paths are storable. Anything with a scheme, a
    protocol-relative prefix, or a backslash is dropped rather than sanitised,
    so a malformed route degrades to 'no link' instead of becoming an open
    redirect."""
    route = (route or '').strip()
    if not route:
        return ''
    if not route.startswith('/') or route.startswith('//') or route.startswith('/\\'):
        return ''
    if ':' in route.split('?', 1)[0] or '\\' in route:
        return ''
    return route[:200]


# ---------------------------------------------------------------------------
# Core primitives
# ---------------------------------------------------------------------------

def create_notification(*, recipient, notification_type, title, message,
                        related_entity_type='', related_entity_id=None,
                        action_route='', priority=Notification.Priority.NORMAL,
                        dedupe_key=''):
    """Creates one notification, or returns the existing one when `dedupe_key`
    has already been used. Returns None when there is no recipient (e.g. a
    department with no Event Coordinator yet) — that is a normal condition, not an error."""
    if recipient is None:
        return None

    payload = dict(
        recipient=recipient,
        notification_type=notification_type,
        title=title[:200],
        message=message,
        related_entity_type=related_entity_type[:40],
        related_entity_id=related_entity_id,
        action_route=_clean_route(action_route),
        priority=priority,
        dedupe_key=dedupe_key[:200],
    )

    if not dedupe_key:
        return Notification.objects.create(**payload)

    try:
        notification, _created = Notification.objects.get_or_create(
            dedupe_key=payload['dedupe_key'], defaults=payload,
        )
        return notification
    except IntegrityError:
        # Lost a race against a concurrent identical delivery; the other one won.
        return Notification.objects.filter(dedupe_key=payload['dedupe_key']).first()


def create_bulk_notifications(*, recipients, **kwargs):
    """Fans one message out to several recipients, skipping duplicates. Used
    only where the recipient set is genuinely bounded (e.g. the students
    registered for one cancelled event) — never for "all students"."""
    created = []
    base_key = kwargs.pop('dedupe_key', '')
    for recipient in recipients:
        key = f'{base_key}:user{recipient.id}' if base_key else ''
        notification = create_notification(recipient=recipient, dedupe_key=key, **kwargs)
        if notification is not None:
            created.append(notification)
    return created


def mark_read(*, notification, user):
    """Marks one notification read. The caller must already have established
    that `user` is the recipient (the viewset's queryset does); this re-checks
    as defence in depth. `read_at` is always the server clock."""
    if notification.recipient_id != user.id:
        return None
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
    return notification


def mark_all_read(*, user):
    """Marks every one of this user's unread notifications read. Returns the
    number actually changed."""
    return Notification.objects.filter(recipient=user, is_read=False).update(
        is_read=True, read_at=timezone.now(),
    )


def unread_count(*, user) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).count()


def schedule(fn, *args, **kwargs):
    """Runs a notification helper after the surrounding transaction commits.

    Business services call this instead of invoking helpers directly, so the
    notification is never written inside the same transaction as the decision
    it describes — if that transaction rolls back, no notification is sent, and
    if the notification fails, the decision is already durable."""
    transaction.on_commit(lambda: fn(*args, **kwargs))


# ---------------------------------------------------------------------------
# Semantic helpers — one per business event
# ---------------------------------------------------------------------------

@_safe
def notify_registration_submitted(*, registration_request):
    """Tells the department's active Event Coordinator that someone is waiting for approval.
    Silently does nothing when the department has no Event Coordinator yet (the first-Event Coordinator
    provisioning case)."""
    from apps.accounts.models import User

    event_coordinator = User.objects.filter(
        role=User.Role.EVENT_COORDINATOR, is_active=True, department_id=registration_request.department_id,
    ).first()
    return create_notification(
        recipient=event_coordinator,
        notification_type=Notification.Type.REGISTRATION_SUBMITTED,
        title='New registration request',
        message=f'{registration_request.user.username} requested a {registration_request.role} account '
                f'in {registration_request.department.name}.',
        related_entity_type='registrationrequest', related_entity_id=registration_request.id,
        action_route='/event_coordinator',
        dedupe_key=f'regreq:{registration_request.id}:submitted',
    )


@_safe
def notify_registration_decision(*, registration_request):
    """Tells the applicant the outcome. The rejection reason is included
    because the applicant needs it to act; nothing else about the review is
    exposed."""
    approved = registration_request.status == registration_request.Status.APPROVED
    if approved:
        title = 'Registration approved'
        message = 'Your account has been approved. You can now sign in.'
    else:
        title = 'Registration rejected'
        reason = registration_request.rejection_reason or 'No reason was provided.'
        message = f'Your registration request was rejected. Reason: {reason}'

    return create_notification(
        recipient=registration_request.user,
        notification_type=(
            Notification.Type.REGISTRATION_APPROVED if approved else Notification.Type.REGISTRATION_REJECTED
        ),
        title=title,
        message=message,
        related_entity_type='registrationrequest', related_entity_id=registration_request.id,
        action_route='/login',
        priority=Notification.Priority.HIGH,
        dedupe_key=f'regreq:{registration_request.id}:decision',
    )


@_safe
def notify_event_cancelled(*, event):
    """Mandatory per the spec: every student with a live registration for a
    cancelled event is told. The recipient set is bounded by the event's own
    registrations, so this can never become a system-wide broadcast."""
    from apps.registrations.models import Registration

    students = [
        registration.student
        for registration in Registration.objects.filter(
            event=event, status=Registration.Status.REGISTERED,
        ).select_related('student')
    ]
    return create_bulk_notifications(
        recipients=students,
        notification_type=Notification.Type.EVENT_CANCELLED,
        title=f'Event cancelled: {event.title}',
        message=f'"{event.title}" scheduled for {event.event_date} has been cancelled.',
        related_entity_type='event', related_entity_id=event.id,
        action_route='/student/registrations',
        priority=Notification.Priority.HIGH,
        dedupe_key=f'event:{event.id}:cancelled',
    )


@_safe
def notify_event_published(*, event):
    """Tells students in the managing department that a new event is open.

    Deliberately scoped to the event's own department rather than every
    student in the system — an Admin-created event has no department and so
    notifies nobody, which is the correct conservative behaviour for a
    broadcast-shaped message.
    """
    from apps.accounts.models import User

    if event.department_id is None:
        return []

    students = list(User.objects.filter(
        role=User.Role.STUDENT, is_active=True, department_id=event.department_id,
    ))
    return create_bulk_notifications(
        recipients=students,
        notification_type=Notification.Type.EVENT_PUBLISHED,
        title=f'New event: {event.title}',
        message=f'"{event.title}" on {event.event_date} at {event.venue} is now published.',
        related_entity_type='event', related_entity_id=event.id,
        action_route=f'/student/events/{event.id}',
        dedupe_key=f'event:{event.id}:published',
    )


@_safe
def notify_evidence_decision(*, evidence, decision, reason, is_override=False, reviewer=None):
    """Tells the owning student what Faculty (or an overriding Event Coordinator) decided.

    Only the decision and the reviewer's own stated reason are included — no
    GPS coordinates, no hashes, no capture metadata, nothing another party
    could not already see on their own evidence page.
    """
    type_map = {
        'VERIFIED': Notification.Type.EVIDENCE_VERIFIED,
        'REJECTED': Notification.Type.EVIDENCE_REJECTED,
        'RESUBMISSION_REQUIRED': Notification.Type.EVIDENCE_RESUBMISSION_REQUIRED,
    }
    notification_type = Notification.Type.EVENT_COORDINATOR_OVERRIDE if is_override else type_map.get(decision)
    if notification_type is None:
        return None

    participation = evidence.participation
    event_title = participation.event.title
    version_number = evidence.current_version.version_number if evidence.current_version else 0

    if is_override:
        title = f'Verification overridden: {event_title}'
        message = f'Your Event Coordinator reviewed the Faculty decision for "{event_title}" and recorded {decision}.'
    elif decision == 'VERIFIED':
        title = f'Evidence verified: {event_title}'
        message = f'Your participation evidence for "{event_title}" has been verified.'
    elif decision == 'REJECTED':
        title = f'Evidence rejected: {event_title}'
        message = f'Your participation evidence for "{event_title}" was rejected.'
    else:
        title = f'Resubmission required: {event_title}'
        message = f'Faculty asked you to resubmit evidence for "{event_title}".'

    if reason:
        message = f'{message} Reason: {reason}'

    route = (
        f'/student/participation/{participation.id}/resubmit'
        if notification_type == Notification.Type.EVIDENCE_RESUBMISSION_REQUIRED
        else '/student/participation'
    )
    return create_notification(
        recipient=participation.student,
        notification_type=notification_type,
        title=title,
        message=message,
        related_entity_type='evidence', related_entity_id=evidence.id,
        action_route=route,
        priority=Notification.Priority.HIGH,
        # Version-scoped so a genuine second resubmission request on a later
        # version is still delivered, while a retry of the same one is not.
        dedupe_key=f'evidence:{evidence.id}:v{version_number}:{notification_type}',
    )


def _attendance_event(attendance):
    """The event an attendance record belongs to.

    Read through the registration, which every record has. The participation
    is null whenever the Event Coordinator marked a student who never
    captured, and reaching through it there would raise — silently, because
    these helpers are wrapped in @_safe, leaving the student with no
    notification at all.
    """
    if attendance.registration_id is not None:
        return attendance.registration.event
    return attendance.participation.event


def _attendance_student(attendance):
    if attendance.registration_id is not None:
        return attendance.registration.student
    return attendance.participation.student


@_safe
def notify_attendance_request(*, attendance):
    """Tells the department Event Coordinator that an attendance request is waiting."""
    from apps.accounts.models import User

    event_coordinator = User.objects.filter(
        role=User.Role.EVENT_COORDINATOR, is_active=True,
        department_id=_attendance_event(attendance).department_id,
    ).first()
    student = _attendance_student(attendance)
    return create_notification(
        recipient=event_coordinator,
        notification_type=Notification.Type.ATTENDANCE_REQUESTED,
        title='Attendance approval needed',
        message=f'{attendance.requested_by.username} requested attendance for {student.username} '
                f'({_attendance_event(attendance).title}).',
        related_entity_type='attendance', related_entity_id=attendance.id,
        action_route='/event_coordinator/attendance',
        dedupe_key=f'attendance:{attendance.id}:requested',
    )


@_safe
def notify_attendance_decision(*, attendance):
    """Tells the student and the Faculty member who raised the request."""
    approved = attendance.status == attendance.Status.APPROVED
    event_title = _attendance_event(attendance).title
    notification_type = (
        Notification.Type.ATTENDANCE_APPROVED if approved else Notification.Type.ATTENDANCE_REJECTED
    )
    verb = 'approved' if approved else 'rejected'
    message = f'Attendance for "{event_title}" was {verb}.'
    if not approved and attendance.rejection_reason:
        message = f'{message} Reason: {attendance.rejection_reason}'

    created = []
    student = create_notification(
        recipient=_attendance_student(attendance),
        notification_type=notification_type,
        title=f'Attendance {verb}',
        message=message,
        related_entity_type='attendance', related_entity_id=attendance.id,
        action_route='/student/attendance',
        priority=Notification.Priority.HIGH,
        dedupe_key=f'attendance:{attendance.id}:decision:student',
    )
    if student:
        created.append(student)

    faculty = create_notification(
        recipient=attendance.requested_by,
        notification_type=notification_type,
        title=f'Attendance {verb}',
        message=f'Your attendance request for {_attendance_student(attendance).username} '
                f'("{event_title}") was {verb}.',
        related_entity_type='attendance', related_entity_id=attendance.id,
        action_route='/faculty/attendance-requests',
        dedupe_key=f'attendance:{attendance.id}:decision:faculty',
    )
    if faculty:
        created.append(faculty)
    return created


@_safe
def notify_od_request(*, od_request):
    from apps.accounts.models import User

    event_coordinator = User.objects.filter(
        role=User.Role.EVENT_COORDINATOR, is_active=True,
        department_id=od_request.participation.event.department_id,
    ).first()
    student = od_request.participation.student
    return create_notification(
        recipient=event_coordinator,
        notification_type=Notification.Type.OD_REQUESTED,
        title='OD approval needed',
        message=f'{od_request.requested_by.username} requested OD for {student.username} '
                f'({od_request.participation.event.title}).',
        related_entity_type='odrequest', related_entity_id=od_request.id,
        action_route='/event_coordinator/od',
        dedupe_key=f'od:{od_request.id}:requested',
    )


@_safe
def notify_od_decision(*, od_request):
    approved = od_request.status == od_request.Status.APPROVED
    event_title = od_request.participation.event.title
    notification_type = Notification.Type.OD_APPROVED if approved else Notification.Type.OD_REJECTED
    verb = 'approved' if approved else 'rejected'
    message = f'Your OD request for "{event_title}" was {verb}.'
    if not approved and od_request.rejection_reason:
        message = f'{message} Reason: {od_request.rejection_reason}'

    created = []
    student = create_notification(
        recipient=od_request.participation.student,
        notification_type=notification_type,
        title=f'OD {verb}',
        message=message,
        related_entity_type='odrequest', related_entity_id=od_request.id,
        action_route='/student/od',
        priority=Notification.Priority.HIGH,
        dedupe_key=f'od:{od_request.id}:decision:student',
    )
    if student:
        created.append(student)

    faculty = create_notification(
        recipient=od_request.requested_by,
        notification_type=notification_type,
        title=f'OD {verb}',
        message=f'Your OD request for {od_request.participation.student.username} '
                f'("{event_title}") was {verb}.',
        related_entity_type='odrequest', related_entity_id=od_request.id,
        action_route='/faculty/od-requests',
        dedupe_key=f'od:{od_request.id}:decision:faculty',
    )
    if faculty:
        created.append(faculty)
    return created


@_safe
def notify_certificate_submitted(*, certificate):
    """Tells the Faculty of the student's department that a certificate is
    waiting for verification.

    Addressed to Faculty rather than to one named reviewer because the
    project has no per-event reviewer assignment: any Faculty member in the
    department may pick it up, exactly as they do for evidence.
    """
    from apps.accounts.models import User

    participation = certificate.participation
    event_title = participation.event.title

    # A department-less (Admin-created) event has no Faculty cohort to notify,
    # and filtering on department_id=None would match every Faculty account
    # that happens to have no department — the same guard notify_event_published
    # applies.
    if participation.event.department_id is None:
        return None

    # Scoped to the event's department, not the student's: that is the scope
    # the certificate permissions use, so notifying on any other basis would
    # send a reviewer to a record they get a 404 from.
    recipients = User.objects.filter(
        role=User.Role.FACULTY,
        is_active=True,
        department_id=participation.event.department_id,
    )
    if not recipients:
        return None

    return create_bulk_notifications(
        recipients=recipients,
        notification_type=Notification.Type.CERTIFICATE_SUBMITTED,
        title=f'Certificate to verify: {event_title}',
        message=(
            f'{participation.student.full_name or participation.student.username} submitted a '
            f'certificate for "{event_title}" (attempt {certificate.attempt_number}).'
        ),
        related_entity_type='certificate', related_entity_id=certificate.id,
        action_route=f'/faculty/certificates/{certificate.id}',
        priority=Notification.Priority.NORMAL,
        dedupe_key=f'certificate:{certificate.id}:submitted',
    )


@_safe
def notify_certificate_decision(*, certificate):
    """Tells the student what was decided about their certificate, including
    the rejection reason, which they need in order to act on it."""
    type_map = {
        'VERIFIED': Notification.Type.CERTIFICATE_VERIFIED,
        'REJECTED': Notification.Type.CERTIFICATE_REJECTED,
        'ACCEPTED_BY_COORDINATOR': Notification.Type.CERTIFICATE_ACCEPTED,
    }
    notification_type = type_map.get(certificate.status)
    if notification_type is None:
        return None

    participation = certificate.participation
    event_title = participation.event.title

    if certificate.status == 'VERIFIED':
        title = f'Certificate verified: {event_title}'
        message = f'Your certificate for "{event_title}" has been verified.'
    elif certificate.status == 'REJECTED':
        title = f'Certificate rejected: {event_title}'
        message = f'Your certificate for "{event_title}" was rejected.'
        if certificate.rejection_reason:
            message = f'{message} Reason: {certificate.rejection_reason}'
    else:
        title = f'Certificate accepted: {event_title}'
        message = (
            f'Your Event Coordinator accepted the certificate you submitted for "{event_title}".'
        )

    return create_notification(
        recipient=participation.student,
        notification_type=notification_type,
        title=title,
        message=message,
        related_entity_type='certificate', related_entity_id=certificate.id,
        action_route='/student/certificates',
        priority=Notification.Priority.HIGH,
        # Attempt-scoped: a decision on a later attempt is a genuinely new
        # notification, a retry of the same one is not.
        dedupe_key=f'certificate:{certificate.id}:{certificate.status}',
    )


@_safe
def notify_certificate_final_decision(*, certificate):
    """Tells the student the Event Coordinator's final decision.

    Separate from the Faculty decision notification: the student already heard
    that the certificate was verified, and this is the different, later fact
    that the coordinator has now accepted or rejected it.
    """
    participation = certificate.participation
    event_title = participation.event.title
    accepted = certificate.final_decision == 'ACCEPTED'

    title = (
        f'Certificate accepted: {event_title}' if accepted
        else f'Certificate rejected: {event_title}'
    )
    message = (
        f'Your Event Coordinator accepted your certificate for "{event_title}".' if accepted
        else f'Your Event Coordinator rejected your certificate for "{event_title}".'
    )
    if not accepted and certificate.final_rejection_reason:
        message = f'{message} Reason: {certificate.final_rejection_reason}'

    return create_notification(
        recipient=participation.student,
        notification_type=(
            Notification.Type.CERTIFICATE_ACCEPTED if accepted
            else Notification.Type.CERTIFICATE_REJECTED
        ),
        title=title,
        message=message,
        related_entity_type='certificate', related_entity_id=certificate.id,
        action_route='/student/certificates',
        priority=Notification.Priority.HIGH,
        dedupe_key=f'certificate:{certificate.id}:final:{certificate.final_decision}',
    )


@_safe
def notify_achievement_pending(*, achievement):
    """Tells the Event Coordinator an achievement is waiting for approval. Only fired for
    records that actually need review — an Event Coordinator/Admin-created achievement is
    authoritative on creation and notifies nobody."""
    from apps.accounts.models import User

    event_coordinator = User.objects.filter(
        role=User.Role.EVENT_COORDINATOR, is_active=True,
        department_id=achievement.participation.event.department_id,
    ).first()
    return create_notification(
        recipient=event_coordinator,
        notification_type=Notification.Type.ACHIEVEMENT_CREATED,
        title='Achievement approval needed',
        message=f'{achievement.created_by.username} recorded "{achievement.title}" for '
                f'{achievement.participation.student.username}.',
        related_entity_type='achievement', related_entity_id=achievement.id,
        action_route='/event_coordinator/achievements',
        dedupe_key=f'achievement:{achievement.id}:pending',
    )


@_safe
def notify_achievement_decision(*, achievement):
    approved = achievement.status == achievement.Status.APPROVED
    notification_type = (
        Notification.Type.ACHIEVEMENT_APPROVED if approved else Notification.Type.ACHIEVEMENT_REJECTED
    )
    verb = 'approved' if approved else 'rejected'
    message = f'"{achievement.title}" was {verb}.'
    if not approved and achievement.rejection_reason:
        message = f'{message} Reason: {achievement.rejection_reason}'

    created = []
    student = create_notification(
        recipient=achievement.participation.student,
        notification_type=notification_type,
        title=f'Achievement {verb}',
        message=(
            f'Your achievement "{achievement.title}" is now official.' if approved else message
        ),
        related_entity_type='achievement', related_entity_id=achievement.id,
        action_route='/student/achievements',
        priority=Notification.Priority.HIGH,
        dedupe_key=f'achievement:{achievement.id}:decision:student',
    )
    if student:
        created.append(student)

    # The creator also hears the outcome — unless they are the reviewer, in
    # which case telling them what they just decided would be noise.
    if achievement.created_by_id != achievement.reviewed_by_id:
        creator = create_notification(
            recipient=achievement.created_by,
            notification_type=notification_type,
            title=f'Achievement {verb}',
            message=message,
            related_entity_type='achievement', related_entity_id=achievement.id,
            action_route='/faculty/achievements',
            dedupe_key=f'achievement:{achievement.id}:decision:creator',
        )
        if creator:
            created.append(creator)
    return created
