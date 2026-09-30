import io

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image

from apps.events.tests.helpers import (
    make_admin, make_college, make_department, make_event, make_faculty, make_event_coordinator, make_student,
)
from apps.events.models import Event
from apps.registrations.models import Registration

__all__ = [
    'make_admin', 'make_college', 'make_department', 'make_event', 'make_faculty', 'make_event_coordinator',
    'make_student',
    'make_registration', 'make_todays_published_event', 'make_registered_student_for_today',
    'make_fake_image_bytes', 'make_uploaded_image', 'iso',
]


def make_registration(*, student, event):
    return Registration.objects.create(student=student, event=event)


def make_todays_published_event(*, created_by, college=None, department=None, title='Live Event', **overrides):
    """A PUBLISHED event whose event_date is today by default — the only
    date on which live participation capture is allowed. Callers may
    override `days_until_event` to deliberately build a non-today event
    (e.g. to test the wrong-date rejection paths), so the "is it today" bit
    is only guaranteed when the caller hasn't overridden that."""
    today = timezone.localdate()
    defaults = dict(
        created_by=created_by,
        college=college,
        department=department,
        title=title,
        status=Event.Status.PUBLISHED,
        days_until_event=0,
        registration_starts_in=-5,
        registration_ends_in=-1,
    )
    defaults.update(overrides)
    event = make_event(**defaults)
    if 'days_until_event' not in overrides:
        assert event.event_date == today
    return event


def make_registered_student_for_today(*, event_coordinator, department, college, username='partstudent'):
    event = make_todays_published_event(created_by=event_coordinator, college=college, department=department)
    student = make_student(username, department)
    registration = make_registration(student=student, event=event)
    return student, event, registration


def make_fake_image_bytes(fmt='JPEG', size=(300, 300), color=(120, 130, 140)) -> bytes:
    buffer = io.BytesIO()
    Image.new('RGB', size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def make_uploaded_image(
    name='capture.jpg', fmt='JPEG', size=(300, 300), content_type='image/jpeg',
) -> SimpleUploadedFile:
    data = make_fake_image_bytes(fmt=fmt, size=size)
    return SimpleUploadedFile(name, data, content_type=content_type)


def iso(dt) -> str:
    return dt.isoformat().replace('+00:00', 'Z')
