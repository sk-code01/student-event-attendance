from django.conf import settings
from django.db import models
from django.db.models import Q


class Attendance(models.Model):
    """
    The official attendance record for a participation, and the request that
    produced it — deliberately one table, not a separate "request" plus a
    separate "final record" table. An APPROVED row *is* the official
    attendance record (`reviewed_by`/`reviewed_at` naming who made it
    official and when); a second FinalAttendance table would duplicate every
    field for no behavioural gain.

    Attendance is keyed on `registration`, not on `participation`. The Event
    Coordinator has to be able to record attendance for a student who never
    submitted a live capture, and such a student has no Participation row at
    all — keying on participation would make that record unrepresentable, and
    inventing an empty Participation to hang it off would corrupt every
    "did they capture?" query in the system.

    `registration` is a `OneToOneField`: exactly one attendance record per
    registration, enforced at the database level rather than by an
    application check. That is also the duplicate-request guard — a second
    request for the same registration cannot be inserted at all.

    `participation` is kept alongside it, and is null exactly when the student
    never captured. Where it is set it is always the participation belonging
    to that same registration.

    `student`/`event` are deliberately NOT duplicated here. `Participation`
    already stores both and re-derives them from its `Registration` on every
    save, so reading them through `participation` is guaranteed consistent,
    while a local copy could drift and would give a malicious client a
    second field to try to spoof (see the project's "derive relationships
    server-side" rule).

    Attendance is completely independent of OD (`apps.od.ODRequest`):
    neither blocks, cancels, converts into, or implies the other.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Event Coordinator Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    registration = models.OneToOneField(
        'registrations.Registration', on_delete=models.PROTECT, related_name='attendance',
        null=True, blank=True,
    )
    participation = models.OneToOneField(
        'participation.Participation', on_delete=models.PROTECT, related_name='attendance',
        null=True, blank=True,
        help_text='Null when the student never submitted a live capture.',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    is_manual = models.BooleanField(
        default=False,
        help_text=(
            'True when the Event Coordinator recorded this directly rather than deciding a '
            'Faculty request. Attendance is never inferred from a registration or a capture.'
        ),
    )

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
        null=True, blank=True,
        help_text=(
            'The Faculty member who requested attendance. Null for a record the Event '
            'Coordinator marked directly, which has no requester. Never client-supplied.'
        ),
    )
    requested_at = models.DateTimeField(auto_now_add=True)

    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        help_text=(
            'The Event Coordinator/Admin who approved or rejected. Server-set from request.user, never '
            'client-supplied.'
        ),
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-requested_at']
        indexes = [models.Index(fields=['status'])]
        constraints = [
            # A rejection must always carry a reason — the same belt-and-braces
            # pattern as verification.EvidenceVerification's
            # reason_required_for_reject_or_resubmission: validated in the
            # service layer AND enforced by the database.
            models.CheckConstraint(
                condition=~Q(status='REJECTED') | ~Q(rejection_reason=''),
                name='attendance_rejection_reason_required',
            ),
            # A decided record always names its reviewer and review time; a
            # pending one never does. This makes "approved by nobody" or
            # "reviewed at an unknown time" unrepresentable.
            models.CheckConstraint(
                condition=(
                    Q(status='PENDING', reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | (~Q(status='PENDING') & Q(reviewed_by__isnull=False, reviewed_at__isnull=False))
                ),
                name='attendance_review_fields_match_status',
            ),
        ]

    def save(self, *args, **kwargs):
        # The registration is the identity of an attendance record, so derive
        # it whenever a caller supplied only the participation — the same
        # "derive relationships server-side" rule Participation applies to its
        # own student/event. Nothing outside this model needs to remember it.
        if self.registration_id is None and self.participation_id is not None:
            self.registration_id = self.participation.registration_id
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Attendance #{self.pk} for participation #{self.participation_id} ({self.status})'

    @property
    def student(self):
        return self.participation.student

    @property
    def event(self):
        return self.participation.event
