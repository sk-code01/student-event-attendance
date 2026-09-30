from django.conf import settings
from django.db import models
from django.db.models import Q


class Achievement(models.Model):
    """
    An official academic achievement record. A verified participation never
    *becomes* an achievement automatically — this row only exists because an
    authorized user deliberately created it, which is the whole point of
    keeping "verified participation" and "achievement" distinct concepts.

    `participation` is a plain ForeignKey, not a OneToOneField: one event can
    legitimately yield more than one achievement for the same student (e.g. a
    placing *and* a special award), and a student obviously accumulates
    achievements across events. No `unique(student, achievement_type)`-style
    constraint is imposed — the business rules do not ask for one and it would
    reject legitimate records. Linking through participation is what lets
    analytics later trace Achievement -> Participation -> Event -> Student
    without a second denormalized copy of student/event here.

    Status workflow, kept as small as the authority model allows:

        Faculty creates  -> DRAFT (editable by its creator) -> PENDING_APPROVAL
                                                            -> APPROVED / REJECTED (Event Coordinator/Admin)
        Event Coordinator/Admin creates -> APPROVED immediately

    An Event Coordinator/Admin already holds the approving authority, so routing their own
    record back through their own approval queue would be an approval loop
    with no reviewer other than themselves. Only APPROVED records are
    official.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PENDING_APPROVAL = 'PENDING_APPROVAL', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    participation = models.ForeignKey(
        'participation.Participation', on_delete=models.PROTECT, related_name='achievements',
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    achievement_type = models.CharField(
        max_length=100, help_text='Free text, consistent with the free-text Event.category convention.',
    )
    achievement_date = models.DateField(
        help_text="Must not predate the event, and must not be in the future — see services.validate_achievement_date.",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+',
        help_text='Server-set from request.user. Never client-supplied.',
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name='+',
        help_text='The Event Coordinator/Admin who approved or rejected. Server-set, never client-supplied.',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-achievement_date', '-created_at']
        indexes = [models.Index(fields=['status'])]
        constraints = [
            models.CheckConstraint(
                condition=~Q(status='REJECTED') | ~Q(rejection_reason=''),
                name='achievement_rejection_reason_required',
            ),
            models.CheckConstraint(
                condition=(
                    Q(status__in=['DRAFT', 'PENDING_APPROVAL'], reviewed_by__isnull=True, reviewed_at__isnull=True)
                    | (Q(status__in=['APPROVED', 'REJECTED']) & Q(reviewed_by__isnull=False, reviewed_at__isnull=False))
                ),
                name='achievement_review_fields_match_status',
            ),
        ]

    def __str__(self):
        return f'Achievement #{self.pk} "{self.title}" ({self.status})'

    @property
    def is_official(self) -> bool:
        return self.status == self.Status.APPROVED

    @property
    def student(self):
        return self.participation.student

    @property
    def event(self):
        return self.participation.event
