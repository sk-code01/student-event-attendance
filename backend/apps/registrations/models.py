from django.conf import settings
from django.db import models


class Registration(models.Model):
    """
    Registration != Participation. This model only records that a student
    registered interest in an event; the later Participation phase (live
    camera + GPS capture on the event date) is a separate model with a
    Registration 1 -> 0..1 relationship, deliberately not created yet.

    Design decision — no re-registration after cancellation: the unique
    constraint below applies unconditionally to (student, event), not only
    to active rows. Once a student cancels, they cannot register again for
    the same event. Nothing in the project's rules requires supporting
    re-registration, so the simplest behavior was chosen; revisit this if a
    future phase needs it.

    Design decision — event cancellation does not cascade a status change
    onto existing registrations. A REGISTERED row stays REGISTERED even if
    its event later becomes CANCELLED; the event's own `status` is the
    single source of truth for "this event was cancelled", which the
    student sees via the nested event data on their registration.
    """

    class Status(models.TextChoices):
        REGISTERED = 'REGISTERED', 'Registered'
        CANCELLED = 'CANCELLED', 'Cancelled'

    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='registrations',
    )
    event = models.ForeignKey('events.Event', on_delete=models.PROTECT, related_name='registrations')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.REGISTERED)
    # registered_at is the business timestamp for "when this registration
    # became active" (semantically distinct from created_at, the immutable
    # row-creation timestamp) — currently always equal to created_at since
    # re-registration isn't supported, but kept separate for that future case.
    registered_at = models.DateTimeField(auto_now_add=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-registered_at']
        constraints = [
            models.UniqueConstraint(fields=['student', 'event'], name='unique_student_event_registration'),
        ]
        indexes = [models.Index(fields=['status'])]

    def __str__(self):
        return f'{self.student_id} -> event {self.event_id} ({self.status})'
