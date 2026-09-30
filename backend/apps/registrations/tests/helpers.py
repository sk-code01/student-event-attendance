from apps.events.tests.helpers import (
    make_admin, make_college, make_department, make_event, make_faculty, make_event_coordinator, make_student,
)
from apps.registrations.models import Registration

__all__ = [
    'make_admin', 'make_college', 'make_department', 'make_event', 'make_faculty', 'make_event_coordinator',
    'make_student',
    'make_registration',
]


def make_registration(*, student, event, status=Registration.Status.REGISTERED):
    registration = Registration.objects.create(student=student, event=event)
    if status != Registration.Status.REGISTERED:
        registration.status = status
        registration.save(update_fields=['status'])
    return registration
