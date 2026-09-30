from datetime import timedelta

from django.utils import timezone

from apps.accounts.tests.helpers import make_admin, make_department, make_faculty, make_event_coordinator, make_student
from apps.colleges.models import College
from apps.events.models import Event

__all__ = [
    'make_admin', 'make_department', 'make_faculty', 'make_event_coordinator', 'make_student',
    'make_college', 'make_event',
]


def make_college(code='ENGG', name='Engineering College', is_active=True):
    return College.objects.create(code=code, name=name, is_active=is_active)


def make_event(
    *,
    created_by,
    college=None,
    department=None,
    title='Tech Fest',
    status=Event.Status.DRAFT,
    days_until_event=10,
    registration_starts_in=-2,
    registration_ends_in=5,
):
    today = timezone.localdate()
    college = college or make_college()
    return Event.objects.create(
        title=title,
        description='A test event.',
        event_date=today + timedelta(days=days_until_event),
        venue='Main Auditorium',
        category='Technical',
        conducting_college=college,
        department=department,
        created_by=created_by,
        status=status,
        registration_start_date=today + timedelta(days=registration_starts_in),
        registration_end_date=today + timedelta(days=registration_ends_in),
    )
