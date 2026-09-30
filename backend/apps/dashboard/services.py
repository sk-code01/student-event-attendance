"""
Role-aware operational dashboard data.

One service, four role branches — not four near-identical implementations.
Every branch builds its counts server-side with `.count()` / `.aggregate()`
against filtered querysets; no branch ever loads rows into Python to count
them, and no branch sends data outside its role's scope for Angular to filter.

These are *operational* counts only — pending queues, totals, recent items.
Trends, engagement scoring, predictions and charts belong to Phase 7 and are
deliberately absent.

Query budget: each dashboard is a fixed number of aggregate queries
independent of how much data exists, plus two small bounded reads (recent
activity, recent notifications). There is no N+1 here because nothing
iterates a queryset to count a related set.
"""

from django.db.models import Count, Q
from django.utils import timezone

from apps.accounts.models import RegistrationRequest, User
from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.audit.models import AuditLog
from apps.colleges.models import College
from apps.departments.models import Department
from apps.events.models import Event
from apps.notifications.models import Notification
from apps.od.models import ODRequest
from apps.participation.models import Participation
from apps.registrations.models import Registration
from apps.verification.models import Evidence

RECENT_LIMIT = 8

# Evidence that is awaiting a Faculty decision.
_PENDING_EVIDENCE = Q(status__in=[Evidence.Status.SUBMITTED, Evidence.Status.UNDER_REVIEW])


def _recent_activity(*, queryset):
    return list(queryset.select_related('actor')[:RECENT_LIMIT])


def _recent_notifications(*, user):
    return list(Notification.objects.filter(recipient=user)[:RECENT_LIMIT])


def _unread(*, user):
    return Notification.objects.filter(recipient=user, is_read=False).count()


def build_dashboard(*, user):
    """Returns `{role, cards, recent_activity, recent_notifications, unread_notifications}`.

    `cards` is a list of `{key, label, value, route}` so the frontend renders
    whatever the backend decided this role may see, rather than hard-coding a
    per-role card list that could drift out of step with the authorization
    rules."""
    if user.is_superuser or user.role == User.Role.ADMIN:
        payload = _admin(user)
    elif user.role == User.Role.EVENT_COORDINATOR:
        payload = _event_coordinator(user)
    elif user.role == User.Role.FACULTY:
        payload = _faculty(user)
    else:
        payload = _student(user)

    payload['role'] = user.role
    payload['unread_notifications'] = _unread(user=user)
    payload['recent_notifications'] = _recent_notifications(user=user)
    return payload


# ---------------------------------------------------------------- student ---

def _student(user):
    """Own data only. Every queryset below is filtered by `student=user` or
    `participation__student=user`."""
    today = timezone.localdate()

    registrations = Registration.objects.filter(student=user)
    registered_count = registrations.filter(status=Registration.Status.REGISTERED).count()

    upcoming = Event.objects.filter(
        status=Event.Status.PUBLISHED,
        event_date__gte=today,
        registration_start_date__lte=today,
        registration_end_date__gte=today,
    ).count()

    participations = Participation.objects.filter(student=user)
    pending_verification = Evidence.objects.filter(
        _PENDING_EVIDENCE, participation__student=user,
    ).count()
    verified = Evidence.objects.filter(participation__student=user, status=Evidence.Status.VERIFIED).count()

    # Through the registration, not the participation: a manually marked
    # attendance has no participation and would otherwise be missing from the
    # student's own totals.
    attendance = Attendance.objects.filter(registration__student=user).aggregate(
        approved=Count('id', filter=Q(status=Attendance.Status.APPROVED)),
        pending=Count('id', filter=Q(status=Attendance.Status.PENDING)),
    )
    od = ODRequest.objects.filter(participation__student=user).aggregate(
        approved=Count('id', filter=Q(status=ODRequest.Status.APPROVED)),
        pending=Count('id', filter=Q(status=ODRequest.Status.PENDING)),
    )
    achievements = Achievement.objects.filter(
        participation__student=user, status=Achievement.Status.APPROVED,
    ).count()

    return {
        'cards': [
            _card('open_events', 'Open Events', upcoming, '/student/events'),
            _card('registered_events', 'Registered Events', registered_count, '/student/registrations'),
            _card('participations', 'Participations', participations.count(), '/student/participation'),
            _card('pending_verification', 'Pending Verification', pending_verification, '/student/participation'),
            _card('verified_evidence', 'Verified Evidence', verified, '/student/participation'),
            _card('attendance_approved', 'Attendance Approved', attendance['approved'], '/student/attendance'),
            _card('attendance_pending', 'Attendance Pending', attendance['pending'], '/student/attendance'),
            _card('od_approved', 'OD Approved', od['approved'], '/student/od'),
            _card('od_pending', 'OD Pending', od['pending'], '/student/od'),
            _card('achievements', 'Official Achievements', achievements, '/student/achievements'),
        ],
        'recent_activity': _recent_activity(queryset=AuditLog.objects.filter(actor=user)),
    }


# ---------------------------------------------------------------- faculty ---

def _faculty(user):
    """Department-scoped, matching exactly the scope Faculty already have on
    the evidence/attendance/OD/achievement endpoints. A Faculty account with
    no department sees zeros rather than everything department-less."""
    scope = Q(participation__event__department_id=user.department_id) if user.department_id else Q(pk__in=[])
    evidence_scope = Q(participation__event__department_id=user.department_id) if user.department_id else Q(pk__in=[])
    # Attendance is keyed on the registration, so it needs its own scope;
    # reusing the participation-based one would hide every manually marked
    # record.
    attendance_scope = (
        Q(registration__event__department_id=user.department_id) if user.department_id else Q(pk__in=[])
    )

    pending_evidence = Evidence.objects.filter(_PENDING_EVIDENCE).filter(evidence_scope).count()
    verified_evidence = Evidence.objects.filter(evidence_scope, status=Evidence.Status.VERIFIED).count()
    pending_attendance = Attendance.objects.filter(attendance_scope, status=Attendance.Status.PENDING).count()
    pending_od = ODRequest.objects.filter(scope, status=ODRequest.Status.PENDING).count()
    pending_achievements = Achievement.objects.filter(
        scope, status=Achievement.Status.PENDING_APPROVAL,
    ).count()
    my_achievements = Achievement.objects.filter(scope, created_by=user).count()

    return {
        'cards': [
            _card('pending_evidence', 'Evidence Awaiting Review', pending_evidence, '/faculty/verification'),
            _card('verified_evidence', 'Verified Evidence', verified_evidence, '/faculty/verification'),
            _card(
                'pending_attendance', 'Attendance Awaiting Event Coordinator', pending_attendance,
                '/faculty/attendance-requests',
            ),
            _card('pending_od', 'OD Awaiting Event Coordinator', pending_od, '/faculty/od-requests'),
            _card(
                'pending_achievements', 'Achievements Awaiting Event Coordinator', pending_achievements,
                '/faculty/achievements',
            ),
            _card('my_achievements', 'Achievements I Recorded', my_achievements, '/faculty/achievements'),
        ],
        'recent_activity': _recent_activity(queryset=AuditLog.objects.filter(actor=user)),
    }


# -------------------------------------------------------------------- event_coordinator ---

def _event_coordinator(user):
    """Own department only — never system-wide. Recent activity is scoped to
    actors in the same department."""
    department_id = user.department_id
    scope = Q(participation__event__department_id=department_id) if department_id else Q(pk__in=[])
    attendance_scope = (
        Q(registration__event__department_id=department_id) if department_id else Q(pk__in=[])
    )

    pending_registrations = RegistrationRequest.objects.filter(
        status=RegistrationRequest.Status.PENDING, department_id=department_id,
    ).count() if department_id else 0

    events = Event.objects.filter(department_id=department_id) if department_id else Event.objects.none()
    event_counts = events.aggregate(
        total=Count('id'),
        published=Count('id', filter=Q(status=Event.Status.PUBLISHED)),
    )

    pending_evidence = Evidence.objects.filter(_PENDING_EVIDENCE).filter(scope).count()
    pending_attendance = Attendance.objects.filter(attendance_scope, status=Attendance.Status.PENDING).count()
    pending_od = ODRequest.objects.filter(scope, status=ODRequest.Status.PENDING).count()
    pending_achievements = Achievement.objects.filter(
        scope, status=Achievement.Status.PENDING_APPROVAL,
    ).count()

    activity = (
        AuditLog.objects.filter(Q(actor__department_id=department_id) | Q(actor=user))
        if department_id else AuditLog.objects.filter(actor=user)
    )

    return {
        'cards': [
            _card('pending_registrations', 'Registration Approvals', pending_registrations, '/event_coordinator'),
            _card('department_events', 'Department Events', event_counts['total'], '/event_coordinator/events'),
            _card('published_events', 'Published Events', event_counts['published'], '/event_coordinator/events'),
            _card('pending_evidence', 'Evidence Under Review', pending_evidence, '/event_coordinator/verification'),
            _card('pending_attendance', 'Attendance Approvals', pending_attendance, '/event_coordinator/attendance'),
            _card('pending_od', 'OD Approvals', pending_od, '/event_coordinator/od'),
            _card(
                'pending_achievements', 'Achievement Approvals', pending_achievements,
                '/event_coordinator/achievements',
            ),
        ],
        'recent_activity': _recent_activity(queryset=activity),
    }


# ------------------------------------------------------------------ admin ---

def _admin(user):
    """System-wide operational totals."""
    users = User.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(is_active=True)),
    )
    attendance_pending = Attendance.objects.filter(status=Attendance.Status.PENDING).count()
    od_pending = ODRequest.objects.filter(status=ODRequest.Status.PENDING).count()

    return {
        'cards': [
            # A card's route must lead to a page that shows *that* count. The
            # user cards deep-link into user management with the matching
            # filter already applied, so "Active Users: 12" and the page it
            # opens always agree.
            _card('total_users', 'Total Users', users['total'], '/admin/users'),
            _card('active_users', 'Active Users', users['active'], '/admin/users',
                  query={'status': 'active'}),
            # Departments and Event Coordinator provisioning live on the Admin area page.
            _card('departments', 'Departments', Department.objects.count(), '/admin'),
            _card('colleges', 'Colleges', College.objects.count(), '/admin/colleges'),
            _card('events', 'Events', Event.objects.count(), '/admin/events'),
            _card('registrations', 'Registrations', Registration.objects.count(), '/admin/events'),
            # Participation and verification are NOT attendance -- that
            # distinction is the spine of this system, so these must not send
            # an Admin to the attendance screen. Analytics is where the
            # system-wide participation and verification figures live.
            _card('participations', 'Participations', Participation.objects.count(), '/analytics'),
            _card('pending_verification', 'Pending Verification',
                  Evidence.objects.filter(_PENDING_EVIDENCE).count(), '/analytics'),
            _card('pending_attendance', 'Pending Attendance', attendance_pending, '/admin/attendance'),
            _card('pending_od', 'Pending OD', od_pending, '/admin/od'),
            _card('achievements', 'Achievements', Achievement.objects.count(), '/admin/achievements'),
            _card('pending_achievements', 'Pending Achievements',
                  Achievement.objects.filter(status=Achievement.Status.PENDING_APPROVAL).count(),
                  '/admin/achievements'),
        ],
        'recent_activity': _recent_activity(queryset=AuditLog.objects.all()),
    }


def _card(key, label, value, route, query=None):
    """One dashboard card.

    `route` is an internal Angular path and never contains a query string:
    Angular's `routerLink` treats a bare string as a single path segment, so
    "/admin/users?status=active" would be encoded into the path rather than
    parsed. Query parameters therefore travel separately in `query`, which
    the template binds to `[queryParams]`.
    """
    return {'key': key, 'label': label, 'value': value or 0, 'route': route, 'query': query or {}}
