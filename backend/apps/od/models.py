from django.conf import settings
from django.db import models
from django.db.models import Q


class ODRequest(models.Model):
    """
    An On-Duty request raised by Faculty against a verified participation and
    decided by the Event Coordinator.

    OD is a **separate academic workflow from attendance** — it is emphatically
    not `Attendance.status = 'OD'`. The two live in different apps, different
    tables and different approval records: a participation may have attendance
    approved and OD rejected, both approved, either alone, or neither. Nothing
    in this app reads or writes `apps.attendance`, and nothing there reads or
    writes this — that independence is the point.

    Structure otherwise mirrors `apps.attendance.Attendance` on purpose (same
    status set, same server-set reviewer/review-timestamp fields, same
    one-record-per-participation `OneToOneField` duplicate guard, same
    student/event derived through `participation` rather than duplicated),
    so the two workflows stay predictable without being coupled.
    """

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Event Coordinator Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    participation = models.OneToOneField(
        'participation.Participation', on_delete=models.PROTECT, related_name='od_request',
    )
    reason = models.TextField(
        help_text='Why on-duty is being requested — the justification the Event Coordinator reviews. Required.',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
        help_text='The Faculty member who requested OD. Never client-supplied.',
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
            models.CheckConstraint(
                condition=~Q(reason=''),
                name='od_reason_required',
            ),
            models.CheckConstraint(
                condition=~Q(status='REJECTED') | ~Q(rejection_reason=''),
                name='od_rejection_reason_required',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status='PENDING', reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | (~Q(status='PENDING') & Q(reviewed_by__isnull=False, reviewed_at__isnull=False))
                ),
                name='od_review_fields_match_status',
            ),
        ]

    def __str__(self):
        return f'OD request #{self.pk} for participation #{self.participation_id} ({self.status})'

    @property
    def student(self):
        return self.participation.student

    @property
    def event(self):
        return self.participation.event
