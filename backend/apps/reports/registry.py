"""
The report allowlist.

Report type and format both come from this closed registry — never from user
input used to build a path, a module name, or a filename. There is no
filesystem path anywhere in the report pipeline: reports are generated in
memory and streamed to the caller, so there is nothing to traverse and nothing
left on disk in a publicly reachable place.

Each entry declares which roles may run it. That is a UX/dispatch convenience;
the real boundary is that every dataset builder draws from `AnalyticsScope`,
which applies the caller's role scope to the database query itself.
"""

from apps.accounts.models import User

CSV = 'csv'
XLSX = 'xlsx'
PDF = 'pdf'
FORMATS = (CSV, XLSX, PDF)

STUDENT = User.Role.STUDENT
FACULTY = User.Role.FACULTY
EVENT_COORDINATOR = User.Role.EVENT_COORDINATOR
ADMIN = User.Role.ADMIN

ALL_STAFF = (FACULTY, EVENT_COORDINATOR, ADMIN)
EVERYONE = (STUDENT, FACULTY, EVENT_COORDINATOR, ADMIN)


class ReportDefinition:
    def __init__(self, key, title, roles, builder_name, description):
        self.key = key
        self.title = title
        self.roles = roles
        self.builder_name = builder_name
        self.description = description

    def allows(self, user) -> bool:
        if user.is_superuser:
            return True
        return user.role in self.roles


# The report types available. The original 12 from the earlier phase, plus
# the certificate and tracking reports requirements 24 and 25 ask for. Structurally similar
# reports share a builder where that is honest (the four student reports are
# distinct identities over distinct datasets, so each has its own builder);
# none of these is a duplicate of another.
REPORTS = {
    definition.key: definition
    for definition in [
        ReportDefinition(
            'student-participation', 'Student Participation Report', EVERYONE,
            'student_participation',
            'One row per participation, with its event and effective verification outcome.',
        ),
        ReportDefinition(
            'student-achievement', 'Student Achievement Report', EVERYONE,
            'student_achievement',
            'Achievement records with status; only APPROVED rows are official.',
        ),
        ReportDefinition(
            'student-attendance', 'Student Attendance Report', EVERYONE,
            'student_attendance',
            'Attendance requests and their Event Coordinator decisions.',
        ),
        ReportDefinition(
            'student-od', 'Student OD Report', EVERYONE,
            'student_od',
            'On-Duty requests and their Event Coordinator decisions, independent of attendance.',
        ),
        ReportDefinition(
            'event', 'Event Report', ALL_STAFF,
            'event',
            'One row per event with registration and participation counts.',
        ),
        ReportDefinition(
            'registration', 'Registration Report', ALL_STAFF,
            'registration',
            'Registrations with their current status.',
        ),
        ReportDefinition(
            'participation', 'Participation Report', ALL_STAFF,
            'participation',
            'Participations across the authorized scope.',
        ),
        ReportDefinition(
            'verification', 'Verification Report', ALL_STAFF,
            'verification',
            'Evidence submissions with the effective verification decision.',
        ),
        ReportDefinition(
            'attendance-od-summary', 'Attendance/OD Summary Report', ALL_STAFF,
            'attendance_od_summary',
            'Per-event attendance and OD decision counts, reported side by side but never merged.',
        ),
        ReportDefinition(
            'achievement', 'Achievement Report', ALL_STAFF,
            'achievement',
            'Achievements across the authorized scope.',
        ),
        ReportDefinition(
            'certificate', 'Certificate Report', EVERYONE,
            'certificate',
            'Certificate submissions with the Faculty decision and the Event Coordinator final decision.',
        ),
        ReportDefinition(
            'event-tracking', 'Event Tracking Report', ALL_STAFF,
            'event_tracking',
            'Every registered student against each stage: capture, verification, certificate, attendance.',
        ),
        ReportDefinition(
            'department', 'Department Report', (EVENT_COORDINATOR, ADMIN),
            'department',
            'Per-department totals. Event Coordinator sees only their own department.',
        ),
        ReportDefinition(
            'system', 'System/Admin Report', (ADMIN,),
            'system',
            'System-wide operational totals.',
        ),
    ]
}


def get_definition(key: str):
    """Returns the definition for an allowlisted key, or None. A key that is
    not in the registry never reaches any code that could act on it."""
    return REPORTS.get((key or '').strip().lower())


def available_for(user):
    return [d for d in REPORTS.values() if d.allows(user)]
