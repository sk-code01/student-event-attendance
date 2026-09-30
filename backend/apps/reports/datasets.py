"""
Report dataset builders.

Every builder draws its rows from `AnalyticsScope`, the same authorization
boundary analytics uses — so a report can never contain a row the caller could
not already see through the API, and a Student's report is scoped by
`request.user` rather than by any id they might pass.

Columns are chosen deliberately. Reports carry academic and personal
information, so each builder selects named fields; none of them serializes a
model wholesale. Nothing here touches a password, a token, an evidence object
reference, a storage key, a file path or GPS coordinates.
"""

from django.db.models import Count, F, Q

from apps.achievements.models import Achievement
from apps.analytics.scope import AnalyticsScope
from apps.attendance.models import Attendance
from apps.events.models import Event
from apps.od.models import ODRequest


class Dataset:
    """A report's content: a title, ordered column headers, and rows.

    Rows are lists of already-stringified-or-primitive values in the same order
    as `columns`, so every renderer writes identical content and column order
    is stable across formats.
    """

    def __init__(self, *, title, columns, rows, description=''):
        self.title = title
        self.columns = columns
        self.rows = rows
        self.description = description

    @property
    def is_empty(self) -> bool:
        return not self.rows


def _yes_no(value) -> str:
    return 'Yes' if value else 'No'


def _date(value) -> str:
    return value.isoformat() if value else ''


def _datetime(value) -> str:
    """Rendered in the configured application timezone so a report reads the
    same way the UI does."""
    if not value:
        return ''
    from django.utils import timezone
    return timezone.localtime(value).strftime('%Y-%m-%d %H:%M')


# ------------------------------------------------------------- student-side --

def student_participation(scope: AnalyticsScope) -> Dataset:
    rows = [
        [
            p.student.username,
            p.event.title,
            _date(p.event.event_date),
            p.event.category,
            p.status,
            _datetime(p.submitted_at),
            getattr(getattr(p, 'evidence', None), 'status', '') or 'NOT SUBMITTED',
        ]
        for p in scope.participations().select_related('student', 'event', 'evidence')
        .order_by('-event__event_date', 'student__username')
    ]
    return Dataset(
        title='Student Participation Report',
        columns=['Student', 'Event', 'Event Date', 'Category', 'Participation Status',
                 'Submitted At', 'Evidence Outcome'],
        rows=rows,
        description='Evidence Outcome is the effective verification decision (Event Coordinator override wins).',
    )


def student_achievement(scope: AnalyticsScope) -> Dataset:
    rows = [
        [
            a.participation.student.username,
            a.title,
            a.achievement_type,
            _date(a.achievement_date),
            a.participation.event.title,
            a.status,
            _yes_no(a.status == Achievement.Status.APPROVED),
            a.rejection_reason or '',
        ]
        for a in scope.achievements()
        .select_related('participation__student', 'participation__event')
        .order_by('-achievement_date', 'title')
    ]
    return Dataset(
        title='Student Achievement Report',
        columns=['Student', 'Achievement', 'Type', 'Date', 'Event', 'Status', 'Official',
                 'Rejection Reason'],
        rows=rows,
        description='Only APPROVED achievements are official.',
    )


def student_attendance(scope: AnalyticsScope) -> Dataset:
    rows = [
        [
            a.participation.student.username,
            a.participation.event.title,
            _date(a.participation.event.event_date),
            a.status,
            a.requested_by.username,
            _datetime(a.requested_at),
            a.reviewed_by.username if a.reviewed_by_id else '',
            _datetime(a.reviewed_at),
            a.rejection_reason or '',
        ]
        for a in scope.attendance()
        .select_related('participation__student', 'participation__event', 'requested_by', 'reviewed_by')
        .order_by('-requested_at')
    ]
    return Dataset(
        title='Student Attendance Report',
        columns=['Student', 'Event', 'Event Date', 'Status', 'Requested By', 'Requested At',
                 'Reviewed By', 'Reviewed At', 'Rejection Reason'],
        rows=rows,
        description='Only APPROVED rows are official attendance records.',
    )


def student_od(scope: AnalyticsScope) -> Dataset:
    rows = [
        [
            o.participation.student.username,
            o.participation.event.title,
            _date(o.participation.event.event_date),
            o.status,
            o.reason,
            o.requested_by.username,
            _datetime(o.requested_at),
            o.reviewed_by.username if o.reviewed_by_id else '',
            o.rejection_reason or '',
        ]
        for o in scope.od_requests()
        .select_related('participation__student', 'participation__event', 'requested_by', 'reviewed_by')
        .order_by('-requested_at')
    ]
    return Dataset(
        title='Student OD Report',
        columns=['Student', 'Event', 'Event Date', 'Status', 'Reason', 'Requested By',
                 'Requested At', 'Reviewed By', 'Rejection Reason'],
        rows=rows,
        description='On-Duty is independent of attendance; approval of one implies nothing about the other.',
    )


# ----------------------------------------------------------- operational --

def event(scope: AnalyticsScope) -> Dataset:
    Event.objects.mark_past_events_completed()
    # *_count aliases: Event's reverse accessors are already named
    # `registrations`/`participations`, and an annotation cannot shadow them.
    rows = [
        [
            e.title, _date(e.event_date), e.category, e.venue, e.status,
            e.department.name if e.department_id else '(none)',
            e.registration_count, e.participation_count,
        ]
        for e in scope.events()
        .select_related('department')
        .annotate(
            registration_count=Count('registrations', distinct=True),
            participation_count=Count('participations', distinct=True),
        )
        .order_by('-event_date', 'title')
    ]
    return Dataset(
        title='Event Report',
        columns=['Event', 'Date', 'Category', 'Venue', 'Status', 'Department',
                 'Registrations', 'Participations'],
        rows=rows,
        description='Department "(none)" means an Admin-created event that belongs to no department.',
    )


def registration(scope: AnalyticsScope) -> Dataset:
    rows = [
        [
            r.student.username, r.event.title, _date(r.event.event_date), r.event.category,
            r.status, _datetime(r.registered_at), _datetime(r.cancelled_at),
        ]
        for r in scope.registrations().select_related('student', 'event')
        .order_by('-registered_at')
    ]
    return Dataset(
        title='Registration Report',
        columns=['Student', 'Event', 'Event Date', 'Category', 'Status', 'Registered At',
                 'Cancelled At'],
        rows=rows,
        description='Registration is distinct from participation; a registration is not attendance.',
    )


def participation(scope: AnalyticsScope) -> Dataset:
    dataset = student_participation(scope)
    dataset.title = 'Participation Report'
    return dataset


def verification(scope: AnalyticsScope) -> Dataset:
    rows = [
        [
            e.participation.student.username,
            e.participation.event.title,
            _date(e.participation.event.event_date),
            e.status,
            e.current_version.version_number if e.current_version_id else '',
            _datetime(e.current_version.submitted_at) if e.current_version_id else '',
            e.versions.count(),
        ]
        for e in scope.evidence()
        .select_related('participation__student', 'participation__event', 'current_version')
        .prefetch_related('versions')
        .order_by('-created_at')
    ]
    return Dataset(
        title='Verification Report',
        columns=['Student', 'Event', 'Event Date', 'Effective Decision', 'Current Version',
                 'Submitted At', 'Total Versions'],
        rows=rows,
        description='Effective Decision reflects an Event Coordinator override where one exists.',
    )


def attendance_od_summary(scope: AnalyticsScope) -> Dataset:
    """Attendance and OD side by side, per event — reported together for
    convenience but never merged into a single status."""
    attendance_rows = {
        row['event_id']: row
        # Grouped by the registration's event: attendance no longer hangs off
        # the participation, which is null for a manually marked student.
        for row in scope.attendance()
        .values(event_id=F('registration__event__id'), event_title=F('registration__event__title'))
        .annotate(
            requests=Count('id'),
            approved=Count('id', filter=Q(status=Attendance.Status.APPROVED)),
            rejected=Count('id', filter=Q(status=Attendance.Status.REJECTED)),
        )
    }
    od_rows = {
        row['event_id']: row
        for row in scope.od_requests()
        .values(event_id=F('participation__event__id'), event_title=F('participation__event__title'))
        .annotate(
            requests=Count('id'),
            approved=Count('id', filter=Q(status=ODRequest.Status.APPROVED)),
            rejected=Count('id', filter=Q(status=ODRequest.Status.REJECTED)),
        )
    }
    rows = []
    for event_id in sorted(set(attendance_rows) | set(od_rows)):
        a = attendance_rows.get(event_id, {})
        o = od_rows.get(event_id, {})
        rows.append([
            a.get('event_title') or o.get('event_title') or '',
            a.get('requests', 0), a.get('approved', 0), a.get('rejected', 0),
            o.get('requests', 0), o.get('approved', 0), o.get('rejected', 0),
        ])
    return Dataset(
        title='Attendance/OD Summary Report',
        columns=['Event', 'Attendance Requests', 'Attendance Approved', 'Attendance Rejected',
                 'OD Requests', 'OD Approved', 'OD Rejected'],
        rows=rows,
        description='Attendance and OD are independent decisions and are never combined into one status.',
    )


def achievement(scope: AnalyticsScope) -> Dataset:
    dataset = student_achievement(scope)
    dataset.title = 'Achievement Report'
    return dataset


def department(scope: AnalyticsScope) -> Dataset:
    from apps.analytics import services

    payload = services.departments(scope)
    rows = [
        [
            row['department'], row['events'], row['registrations'], row['participations'],
            row['attendance_approved'], row['od_approved'], row['official_achievements'],
        ]
        for row in payload['departments']
    ]
    return Dataset(
        title='Department Report',
        columns=['Department', 'Events', 'Registrations', 'Participations',
                 'Attendance Approved', 'OD Approved', 'Official Achievements'],
        rows=rows,
        description=(
            f"Department-less events: {payload['department_less_events']}. "
            'Admin-created events belong to no department and are not attributed to one.'
        ),
    )


def system(scope: AnalyticsScope) -> Dataset:
    from apps.analytics import services

    overview = services.overview(scope)
    labels = [
        ('Events', 'events'),
        ('Registrations', 'registrations'),
        ('Live registrations', 'live_registrations'),
        ('Participations', 'participations'),
        ('Evidence submitted', 'evidence_submitted'),
        ('Verified participations', 'verified_participations'),
        ('Pending verification', 'pending_verification'),
        ('Attendance requests', 'attendance_requests'),
        ('Attendance approved', 'attendance_approved'),
        ('OD requests', 'od_requests'),
        ('OD approved', 'od_approved'),
        ('Achievements', 'achievements'),
        ('Official achievements', 'official_achievements'),
    ]
    rows = [[label, overview[key]] for label, key in labels]
    rate = overview['participation_rate']
    rows.append(['Participation rate (%)', '—' if rate is None else rate])
    return Dataset(
        title='System/Admin Report',
        columns=['Metric', 'Value'],
        rows=rows,
        description=overview['participation_rate_basis'],
    )


def certificate(scope: AnalyticsScope) -> Dataset:
    """Certificate submissions with both decisions that bear on them: the
    Faculty verification and, where it has been made, the Event Coordinator's
    final decision. They are separate columns because they are separate
    decisions — collapsing them would lose which one rejected a record."""
    rows = [
        [
            c.participation.student.full_name or c.participation.student.username,
            c.participation.student.university_registration_number or '',
            c.participation.event.title,
            _date(c.participation.event.event_date),
            c.attempt_number,
            c.status,
            c.rejection_reason,
            c.final_decision or '',
            c.final_rejection_reason,
            _datetime(c.submitted_at),
        ]
        for c in scope.certificates()
        .select_related('participation__student', 'participation__event')
        .order_by('participation__event__event_date', 'attempt_number')
    ]
    return Dataset(
        title='Certificate Report',
        columns=[
            'Student', 'Registration Number', 'Event', 'Event Date', 'Attempt',
            'Faculty Decision', 'Faculty Reason', 'Coordinator Decision',
            'Coordinator Reason', 'Submitted At',
        ],
        rows=rows,
        description=(
            'Three attempts are allowed per participation. A coordinator decision is only '
            'made after Faculty have verified the certificate.'
        ),
    )


def event_tracking(scope: AnalyticsScope) -> Dataset:
    """Every registered student against every stage of the workflow.

    The exportable form of the tracking view: the same derived statuses, from
    the same code, so an exported spreadsheet can never disagree with what the
    coordinator saw on screen.
    """
    from apps.registrations.tracking import build_row, tracking_queryset

    registrations = tracking_queryset(scope.registrations()).order_by(
        'event__event_date', 'student__username',
    )
    rows = []
    for registration in registrations:
        row = build_row(registration)
        rows.append([
            row['student']['full_name'] or row['student']['username'],
            row['student']['university_registration_number'] or '',
            row['event']['title'],
            _date(row['event']['event_date']),
            row['registration_status'],
            row['live_capture_status'],
            row['live_capture_location'] or '',
            row['verification_status'],
            row['certificate_status'],
            f"{row['certificate_attempts_used']}/"
            f"{row['certificate_attempts_used'] + row['certificate_attempts_remaining']}",
            row['attendance_status'],
        ])
    return Dataset(
        title='Event Tracking Report',
        columns=[
            'Student', 'Registration Number', 'Event', 'Event Date', 'Registration',
            'Live Capture', 'Captured Location', 'Verification', 'Certificate',
            'Certificate Attempts', 'Attendance',
        ],
        rows=rows,
        description=(
            'LIVE CAPTURE NOT_SUBMITTED means the event date passed without a submission; '
            'attendance is never inferred from it.'
        ),
    )


BUILDERS = {
    'student_participation': student_participation,
    'student_achievement': student_achievement,
    'student_attendance': student_attendance,
    'student_od': student_od,
    'event': event,
    'registration': registration,
    'participation': participation,
    'verification': verification,
    'attendance_od_summary': attendance_od_summary,
    'achievement': achievement,
    'department': department,
    'system': system,
    'certificate': certificate,
    'event_tracking': event_tracking,
}


def build(definition, scope: AnalyticsScope) -> Dataset:
    return BUILDERS[definition.builder_name](scope)
