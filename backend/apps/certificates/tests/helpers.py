from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.events.models import Event
from apps.participation.tests.helpers import make_college
from apps.verification.tests.helpers import (
    make_admin,
    make_department,
    make_event_coordinator,
    make_faculty,
    make_participation,
    make_student,
    make_submitted_evidence,
)

__all__ = [
    'make_admin', 'make_department', 'make_event_coordinator', 'make_faculty', 'make_student',
    'make_college', 'make_participation', 'make_submitted_evidence',
    'make_past_event', 'make_pdf_upload', 'make_captured_participation',
]


def make_past_event(*, college, department, days_ago=1, status=Event.Status.COMPLETED):
    """An event whose date has passed, which is when the certificate window is
    open. Registration dates are kept consistent with the event's own
    constraint that registration closes before the event date."""
    event_date = timezone.localdate() - timedelta(days=days_ago)
    return Event.objects.create(
        title=f'Past event {days_ago}d ago',
        description='',
        event_date=event_date,
        venue='Main Hall',
        category='Technical',
        conducting_college=college,
        department=department,
        created_by=department.users.first() or make_admin(f'eventowner{days_ago}'),
        status=status,
        registration_start_date=event_date - timedelta(days=10),
        registration_end_date=event_date - timedelta(days=1),
    )


def make_pdf_upload(name='certificate.pdf'):
    """A minimal but genuinely well-formed PDF, so the validator identifies it
    from its own bytes rather than from the declared content type."""
    buffer = BytesIO()
    buffer.write(b'%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n')
    return SimpleUploadedFile(name, buffer.getvalue(), content_type='application/pdf')


def make_captured_participation(*, student, event):
    """A participation that actually performed and submitted the live capture —
    the precondition for uploading a certificate at all."""
    participation = make_participation(student=student, event=event)
    make_submitted_evidence(participation=participation)
    participation.refresh_from_db()
    return participation
