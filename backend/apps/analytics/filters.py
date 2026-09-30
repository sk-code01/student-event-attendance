"""
Filter parsing and validation for analytics and reports.

The security rule this module exists to enforce: **a query parameter may
narrow what a caller asked for, never widen what they are allowed to see.**
Every id passed in is validated against the caller's own scope *before* it is
used, so `?student=<someone else>` or `?department=<another department>` is
refused rather than honoured.

Validation failures raise DRF exceptions, which surface as 400 for a malformed
value and 403 for an out-of-scope one.
"""

from datetime import datetime

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.departments.models import Department
from apps.events.models import Event

PERIODS = ('daily', 'weekly', 'monthly')
MAX_RANGE_DAYS = 366 * 5  # Five years: generous, but bounded.


def _parse_date(raw, field):
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), '%Y-%m-%d').date()
    except (ValueError, AttributeError):
        raise ValidationError({field: 'Expected an ISO date in YYYY-MM-DD format.'})


class AnalyticsFilters:
    """Validated, scope-checked filters.

    Build with `AnalyticsFilters.from_request(request, user)` — never construct
    from raw query params without validation.
    """

    def __init__(self, *, date_from=None, date_to=None, event=None, category='',
                 department_id=None, student_id=None, period='monthly'):
        self.date_from = date_from
        self.date_to = date_to
        self.event = event
        self.category = category
        self.department_id = department_id
        self.student_id = student_id
        self.period = period

    # -- construction -------------------------------------------------------

    @classmethod
    def from_request(cls, request, *, require_period=False):
        user = request.user
        params = request.query_params
        is_admin = user.is_superuser or user.role == User.Role.ADMIN

        date_from = _parse_date(params.get('date_from'), 'date_from')
        date_to = _parse_date(params.get('date_to'), 'date_to')
        if date_from and date_to:
            if date_from > date_to:
                raise ValidationError({'date_from': 'date_from must not be after date_to.'})
            if (date_to - date_from).days > MAX_RANGE_DAYS:
                raise ValidationError(
                    {'date_from': f'Date range must not exceed {MAX_RANGE_DAYS} days.'},
                )

        period = (params.get('period') or 'monthly').strip().lower()
        if period not in PERIODS:
            raise ValidationError(
                {'period': f'Unsupported period. Choose one of: {", ".join(PERIODS)}.'},
            )

        event = cls._validate_event(params.get('event'), user, is_admin)
        department_id = cls._validate_department(params.get('department'), user, is_admin)
        student_id = cls._validate_student(params.get('student'), user, is_admin)

        return cls(
            date_from=date_from, date_to=date_to, event=event,
            category=(params.get('category') or '').strip(),
            department_id=department_id, student_id=student_id, period=period,
        )

    # -- per-parameter scope checks ----------------------------------------

    @staticmethod
    def _validate_event(raw, user, is_admin):
        """An event outside the caller's scope resolves to 404 — the same
        convention the rest of the project uses, so the filter never confirms
        that an event they cannot see exists."""
        if not raw:
            return None
        if not str(raw).isdigit():
            raise ValidationError({'event': 'Expected a numeric event id.'})
        try:
            event = Event.objects.get(pk=int(raw))
        except Event.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Event not found.')

        if is_admin:
            return event
        if user.role == User.Role.STUDENT:
            if not event.registrations.filter(student=user).exists():
                from rest_framework.exceptions import NotFound
                raise NotFound('Event not found.')
            return event
        # Faculty / Event Coordinator: department scope, with the explicit null guard.
        if user.department_id is None or event.department_id != user.department_id:
            from rest_framework.exceptions import NotFound
            raise NotFound('Event not found.')
        return event

    @staticmethod
    def _validate_department(raw, user, is_admin):
        """Only Admin may name an arbitrary department. An Event Coordinator or Faculty may
        name their own (a no-op narrowing) but never another — that attempt is
        a 403, not a silent fallback to their own data, because silently
        returning different data than was asked for hides the refusal."""
        if not raw:
            return None
        if not str(raw).isdigit():
            raise ValidationError({'department': 'Expected a numeric department id.'})
        department_id = int(raw)

        if not Department.objects.filter(pk=department_id).exists():
            from rest_framework.exceptions import NotFound
            raise NotFound('Department not found.')

        if is_admin:
            return department_id
        if user.role == User.Role.STUDENT:
            raise PermissionDenied('Students cannot filter analytics by department.')
        if user.department_id is None or department_id != user.department_id:
            raise PermissionDenied('You can only request analytics for your own department.')
        return department_id

    @staticmethod
    def _validate_student(raw, user, is_admin):
        """A Student's scope always comes from `request.user`; the parameter is
        refused outright rather than ignored, so a caller is never left
        believing they filtered when they did not.

        Faculty/Event Coordinator may name a student, but only one inside their own
        department; Admin may name anyone.
        """
        if not raw:
            return None
        if not str(raw).isdigit():
            raise ValidationError({'student': 'Expected a numeric student id.'})
        student_id = int(raw)

        if user.role == User.Role.STUDENT and not is_admin:
            if student_id != user.id:
                raise PermissionDenied('You can only view your own analytics.')
            return user.id

        try:
            student = User.objects.get(pk=student_id, role=User.Role.STUDENT)
        except User.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Student not found.')

        if is_admin:
            return student.id
        if user.department_id is None or student.department_id != user.department_id:
            raise PermissionDenied('That student is outside your department.')
        return student.id

    # -- application --------------------------------------------------------

    def apply(self, queryset, *, event_path, date_field):
        """Narrows `queryset` by the validated filters.

        `event_path` is the ORM path from this model to Event ('' when the
        model *is* Event); `date_field` is the field the date range applies to.
        """
        if self.event is not None:
            key = f'{event_path}id' if event_path else 'id'
            queryset = queryset.filter(**{key: self.event.id})
        if self.category:
            queryset = queryset.filter(**{f'{event_path}category__iexact': self.category})
        if self.department_id is not None:
            queryset = queryset.filter(**{f'{event_path}department_id': self.department_id})
        if self.student_id is not None:
            queryset = queryset.filter(self._student_q(event_path))
        if self.date_from:
            queryset = queryset.filter(**{f'{date_field}__date__gte': self.date_from}
                                       if _is_datetime_field(date_field)
                                       else {f'{date_field}__gte': self.date_from})
        if self.date_to:
            queryset = queryset.filter(**{f'{date_field}__date__lte': self.date_to}
                                       if _is_datetime_field(date_field)
                                       else {f'{date_field}__lte': self.date_to})
        return queryset

    def _student_q(self, event_path):
        """The path to the student differs per model, so derive it from the
        event path rather than hard-coding one lookup that would silently
        mis-filter on some models."""
        if event_path == '':
            return Q(registrations__student_id=self.student_id)
        if event_path == 'event__':
            return Q(student_id=self.student_id)
        return Q(participation__student_id=self.student_id)

    def summary(self) -> str:
        """A short, non-sensitive description for the audit log."""
        parts = []
        if self.date_from:
            parts.append(f'from={self.date_from}')
        if self.date_to:
            parts.append(f'to={self.date_to}')
        if self.event is not None:
            parts.append(f'event={self.event.id}')
        if self.category:
            parts.append(f'category={self.category}')
        if self.department_id is not None:
            parts.append(f'department={self.department_id}')
        if self.student_id is not None:
            parts.append(f'student={self.student_id}')
        return ', '.join(parts) or 'no filters'


def _is_datetime_field(name: str) -> bool:
    """`event_date` is a plain DateField; everything else used here is a
    timezone-aware DateTimeField needing a `__date` lookup, which Postgres
    evaluates in the connection's timezone (TIME_ZONE, default Asia/Kolkata)."""
    return name != 'event_date'
