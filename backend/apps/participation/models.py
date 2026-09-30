from django.conf import settings
from django.db import models

# Kept only because apps/participation/migrations/0001_initial.py's
# ParticipationCapture.image field references this name in its frozen
# historical model state (Django's FileField.upload_to is stored as a
# module.attr reference, not a serialized function body) — removing it
# would break `makemigrations`/`migrate` history resolution even though the
# model itself no longer exists. See apps/verification/models.py for its
# Phase 4 replacement (EvidenceCapture.object_reference).
MIME_EXTENSIONS = {
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
}


def capture_upload_path(instance, filename: str) -> str:  # pragma: no cover - historical migration reference only
    extension = MIME_EXTENSIONS.get(instance.mime_type, 'bin')
    return f'{instance.participation.student_id}/{instance.participation_id}/{filename}.{extension}'


class Participation(models.Model):
    """
    Registration != Participation: this row is created only when a student
    actually performs the live capture workflow, never merely because a
    Registration exists. `OneToOneField` on `registration` is the DB-level
    enforcement of "Registration 1 -> 0..1 Participation".

    `student`/`event` are stored redundantly (for query performance and so
    Event Coordinator/Admin can filter without an extra join) but are never independently
    settable — `save()` always re-derives them from `registration`, so they
    can never drift out of sync with it.

    As of Phase 4, evidence capture/versioning/verification lives entirely
    in `apps.verification` (see `Evidence`/`EvidenceVersion`/
    `EvidenceCapture`/`EvidenceVerification`), reachable from here via the
    `evidence` reverse OneToOne. `Participation.status` only tracks whether
    the student has ever opened (DRAFT) and submitted (SUBMITTED) a capture
    session — it is intentionally unaware of verification outcomes, which
    are a distinct concept tracked on `Evidence.status`.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        SUBMITTED = 'SUBMITTED', 'Submitted'

    registration = models.OneToOneField(
        'registrations.Registration', on_delete=models.PROTECT, related_name='participation',
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='participations',
    )
    event = models.ForeignKey('events.Event', on_delete=models.PROTECT, related_name='participations')
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status'])]

    def save(self, *args, **kwargs):
        self.student_id = self.registration.student_id
        self.event_id = self.registration.event_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Participation #{self.pk} ({self.status})'
