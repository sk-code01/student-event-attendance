import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.db.models import Q

MAX_CERTIFICATE_ATTEMPTS = 3

MIME_EXTENSIONS = {
    'application/pdf': 'pdf',
    'image/jpeg': 'jpg',
    'image/png': 'png',
    'image/webp': 'webp',
}

# Same private-storage arrangement as participation evidence: nothing under
# MEDIA_ROOT is web-served, and the only way to read these bytes back is the
# authenticated, authorized download view. See apps/participation/storage.py
# for the full reasoning, which applies identically here.
private_certificate_storage = FileSystemStorage(
    location=str(settings.MEDIA_ROOT / 'certificates'),
    base_url=None,  # deliberate: never generate a public URL for this storage
)


def certificate_upload_path(instance: 'Certificate', filename: str) -> str:
    """Server-generated object key. The client-supplied `filename` is never
    used, which rules out path traversal and storage-key injection."""
    extension = MIME_EXTENSIONS.get(instance.mime_type, 'bin')
    participation = instance.participation
    return (
        f'{participation.student_id}/{participation.id}/'
        f'{instance.attempt_number}/{uuid.uuid4().hex}.{extension}'
    )


class FinalDecision:
    """The Event Coordinator's decision on a Faculty-verified certificate."""

    ACCEPTED = 'ACCEPTED'
    REJECTED = 'REJECTED'

    CHOICES = [(ACCEPTED, 'Accepted'), (REJECTED, 'Rejected')]


class Certificate(models.Model):
    """
    One row per certificate submission attempt, not one per participation.

    A rejected certificate is never overwritten: the next attempt is a new
    row with the next `attempt_number`, so the whole trail — what was
    submitted, who rejected it and why — stays readable. `attempt_number` is
    always server-derived and capped at MAX_CERTIFICATE_ATTEMPTS by both the
    service layer and a database constraint.

    A certificate is attached to a `Participation` rather than to a
    `Registration` on purpose: it is only submittable at all when the student
    actually performed the live capture, and Participation is precisely the
    record that the live capture happened.

    Status, and who may set it:

        student submits            -> SUBMITTED
        Faculty verifies           -> VERIFIED
        Faculty rejects (+reason)  -> REJECTED   (student may resubmit while
                                                  attempts remain)
        Event Coordinator accepts  -> ACCEPTED_BY_COORDINATOR
                                      (only once attempts are exhausted, and
                                      always recorded in the audit trail)
    """

    class Status(models.TextChoices):
        SUBMITTED = 'SUBMITTED', 'Submitted'
        VERIFIED = 'VERIFIED', 'Verified'
        REJECTED = 'REJECTED', 'Rejected'
        ACCEPTED_BY_COORDINATOR = 'ACCEPTED_BY_COORDINATOR', 'Accepted by Event Coordinator'

    participation = models.ForeignKey(
        'participation.Participation', on_delete=models.PROTECT, related_name='certificates',
    )
    attempt_number = models.PositiveIntegerField(
        help_text='1-based, server-derived. Never accepted from the client.',
    )

    object_reference = models.FileField(upload_to=certificate_upload_path, storage=private_certificate_storage)
    original_filename = models.CharField(
        max_length=255, blank=True, default='',
        help_text='Shown to reviewers for recognition only. Never used to build a storage path.',
    )
    mime_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    sha256_hash = models.CharField(max_length=64, db_index=True)

    status = models.CharField(max_length=30, choices=Status.choices, default=Status.SUBMITTED)

    submitted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')
    submitted_at = models.DateTimeField(auto_now_add=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        help_text='The Faculty member who decided, or the Event Coordinator who accepted. Server-set.',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    # --- the Event Coordinator's final decision (requirement 23) -----------
    # A separate layer from `status`, which stays the Faculty-facing state.
    # Keeping them apart means a record still shows both "Faculty verified
    # this" and "the coordinator then accepted/rejected it", rather than one
    # overwriting the other.
    final_decision = models.CharField(
        max_length=20, choices=FinalDecision.CHOICES, blank=True, default='',
        help_text='Blank until the Event Coordinator has made the final decision.',
    )
    final_decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        help_text='The Event Coordinator who made the final decision. Server-set.',
    )
    final_decided_at = models.DateTimeField(null=True, blank=True)
    final_rejection_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['participation_id', 'attempt_number']
        indexes = [models.Index(fields=['status'])]
        constraints = [
            models.UniqueConstraint(
                fields=['participation', 'attempt_number'],
                name='unique_certificate_attempt_per_participation',
            ),
            # The attempt cap is a business rule, so it is enforced where it
            # cannot be bypassed — two concurrent submissions that both read
            # "2 attempts used" cannot both insert attempt 3.
            models.CheckConstraint(
                condition=Q(attempt_number__gte=1) & Q(attempt_number__lte=MAX_CERTIFICATE_ATTEMPTS),
                name='certificate_attempt_number_within_limit',
            ),
            # A rejection always carries its reason, matching the same
            # belt-and-braces rule used for evidence and attendance.
            models.CheckConstraint(
                condition=~Q(status='REJECTED') | ~Q(rejection_reason=''),
                name='certificate_rejection_reason_required',
            ),
            models.CheckConstraint(
                condition=~Q(final_decision='REJECTED') | ~Q(final_rejection_reason=''),
                name='certificate_final_rejection_reason_required',
            ),
        ]

    def __str__(self):
        return f'Certificate attempt {self.attempt_number} for participation #{self.participation_id} ({self.status})'

    @property
    def is_decided(self) -> bool:
        return self.status != self.Status.SUBMITTED

    @property
    def awaits_final_decision(self) -> bool:
        """Faculty have verified it and the coordinator has not yet decided."""
        return self.status == self.Status.VERIFIED and not self.final_decision

    @property
    def is_accepted(self) -> bool:
        """Verified by Faculty, or accepted by the Event Coordinator after the
        attempts ran out. Both mean the certificate stands."""
        return self.status in (self.Status.VERIFIED, self.Status.ACCEPTED_BY_COORDINATOR)
