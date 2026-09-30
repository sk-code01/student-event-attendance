"""
The single authorization boundary for analytics and reports.

Everything in Phase 7 — every metric, every trend, every report row — is built
from a queryset handed out by this module. There is deliberately exactly one
place where "what is this user allowed to aggregate over" is decided, because
a second place is a second opportunity to get it wrong.

Two rules shape it:

**1. Scope is applied before aggregation, never after.** Each accessor returns
an already-filtered queryset, so out-of-scope rows are excluded by the database
and never reach Python, let alone Angular. Aggregating everything and filtering
the numbers afterwards would both leak data and mis-state performance.

**2. Query parameters are never authorization.** A caller may narrow what they
asked for; they can never widen it. `AnalyticsFilters` validates every
requested `student`/`department`/`event` against the role's own scope first, so
passing someone else's id produces a 403/404 rather than their data.

Role scopes match the ones the existing evidence/attendance/OD/achievement APIs
already enforce — analytics does not broaden anyone's access.
"""

from django.db.models import Q

from apps.accounts.models import User
from apps.achievements.models import Achievement
from apps.attendance.models import Attendance
from apps.certificates.models import Certificate
from apps.events.models import Event
from apps.od.models import ODRequest
from apps.participation.models import Participation
from apps.registrations.models import Registration
from apps.verification.models import Evidence

# Evidence still awaiting a Faculty decision.
PENDING_EVIDENCE = Q(status__in=[Evidence.Status.SUBMITTED, Evidence.Status.UNDER_REVIEW])


class AnalyticsScope:
    """Role-scoped querysets over the operational data.

    `filters` is an already-validated `AnalyticsFilters`; by the time it gets
    here every id in it has been checked against this user's own scope.
    """

    def __init__(self, *, user, filters=None):
        self.user = user
        self.filters = filters
        self.is_admin = user.is_superuser or user.role == User.Role.ADMIN
        self.is_event_coordinator = user.role == User.Role.EVENT_COORDINATOR and not self.is_admin
        self.is_faculty = user.role == User.Role.FACULTY and not self.is_admin
        self.is_student = user.role == User.Role.STUDENT and not self.is_admin
        self.department_id = user.department_id

    # -- capability flags ---------------------------------------------------

    @property
    def can_see_departments(self) -> bool:
        """Only Event Coordinator (their own) and Admin (all) get department breakdowns.
        Students and Faculty never receive department comparisons."""
        return self.is_admin or self.is_event_coordinator

    @property
    def can_see_other_students(self) -> bool:
        return not self.is_student

    # -- internal helpers ---------------------------------------------------

    def _staff_department_q(self, prefix: str) -> Q:
        """Department scoping for Faculty/Event Coordinator.

        A staff account with **no** department matches nothing rather than
        implicitly matching every department-less (Admin-created) event, which
        a bare `department_id == None` comparison would do. This mirrors the
        `_in_same_department` guard added to the Phase 5 apps.
        """
        if self.department_id is None:
            return Q(pk__in=[])
        return Q(**{f'{prefix}department_id': self.department_id})

    def _apply_common(self, queryset, *, event_path, date_field):
        """Applies the caller's own requested narrowing (never widening)."""
        if self.filters is None:
            return queryset
        return self.filters.apply(queryset, event_path=event_path, date_field=date_field)

    # -- scoped entity querysets -------------------------------------------

    def events(self):
        """Events the caller may analyse.

        A Student sees the events they actually registered for — an analytics
        view of their own engagement, not a catalogue. Faculty/Event Coordinator see their
        department's events. Admin sees all.

        Note that department-less (Admin-created) events belong to no
        department and therefore appear only for Admin; they are never
        attributed to a department.
        """
        queryset = Event.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(registrations__student=self.user).distinct()
        else:
            queryset = queryset.filter(self._staff_department_q(''))
        return self._apply_common(queryset, event_path='', date_field='event_date')

    def registrations(self):
        queryset = Registration.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('event__'))
        return self._apply_common(queryset, event_path='event__', date_field='registered_at')

    def participations(self):
        queryset = Participation.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('event__'))
        return self._apply_common(queryset, event_path='event__', date_field='created_at')

    def evidence(self):
        queryset = Evidence.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(participation__student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('participation__event__'))
        return self._apply_common(
            queryset, event_path='participation__event__', date_field='created_at',
        )

    def certificates(self):
        """Certificates the caller may analyse.

        Scoped exactly like evidence — through the event's department — so a
        Faculty member and an Event Coordinator see their own department's
        certificates and a student sees only their own.
        """
        queryset = Certificate.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(participation__student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('participation__event__'))
        return self._apply_common(
            queryset, event_path='participation__event__', date_field='submitted_at',
        )

    def attendance(self):
        # Scoped through the registration rather than the participation:
        # attendance is keyed on the registration, and a record the Event
        # Coordinator marked for a student who never captured has no
        # participation at all. Scoping through participation would drop
        # exactly those rows from every analytic and report.
        queryset = Attendance.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(registration__student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('registration__event__'))
        return self._apply_common(
            queryset, event_path='registration__event__', date_field='requested_at',
        )

    def od_requests(self):
        queryset = ODRequest.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(participation__student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('participation__event__'))
        return self._apply_common(
            queryset, event_path='participation__event__', date_field='requested_at',
        )

    def achievements(self):
        queryset = Achievement.objects.all()
        if self.is_admin:
            pass
        elif self.is_student:
            queryset = queryset.filter(participation__student=self.user)
        else:
            queryset = queryset.filter(self._staff_department_q('participation__event__'))
        return self._apply_common(
            queryset, event_path='participation__event__', date_field='created_at',
        )
