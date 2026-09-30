from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class EventQuerySet(models.QuerySet):
    def mark_past_events_completed(self):
        """
        COMPLETED is a real, persisted status (not merely computed at read
        time) so the frontend has one source of truth. Since there is no
        scheduled job in this phase, the transition is applied lazily here —
        called at the top of read operations — which keeps `status` correct
        for any event whose event_date has passed without needing a cron.
        """
        today = timezone.localdate()
        return self.filter(status=Event.Status.PUBLISHED, event_date__lt=today).update(
            status=Event.Status.COMPLETED,
        )


class Event(models.Model):
    """
    `department` is NOT a user-facing field and is never accepted from
    request input. It exists purely as the internal reference that lets Event Coordinator
    authorization reuse the existing Department relationship (per the
    project rule: no FacultyEventAssignment, no new ownership table). It is
    set automatically to the creating Event Coordinator's department, or left null for
    Admin-created (system-wide) events — Admin can manage any event
    regardless of this field.
    """

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        PUBLISHED = 'PUBLISHED', 'Published'
        CANCELLED = 'CANCELLED', 'Cancelled'
        COMPLETED = 'COMPLETED', 'Completed'

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    event_date = models.DateField()
    venue = models.CharField(max_length=200)
    category = models.CharField(max_length=50)
    conducting_college = models.ForeignKey(
        'colleges.College', on_delete=models.PROTECT, related_name='events',
    )
    # Optional geographic coordinates for the venue, used only to calculate
    # a distance warning against a student's live participation capture
    # (Phase 3). The human-readable `venue` field remains authoritative for
    # display; these are validation-only and may be left unset.
    venue_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    venue_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    department = models.ForeignKey(
        'departments.Department',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name='events',
        help_text=(
            'Internal Event Coordinator-authorization scope. Not user-facing; '
            'null means system-wide (Admin-managed).'
        ),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_events',
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    registration_start_date = models.DateField()
    registration_end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering = ['-event_date']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['event_date']),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(registration_end_date__lt=F('event_date')),
                name='registration_end_before_event_date',
            ),
            models.CheckConstraint(
                condition=Q(registration_start_date__lte=F('registration_end_date')),
                name='registration_start_before_or_equal_end',
            ),
        ]

    def __str__(self):
        return f'{self.title} ({self.status})'

    @property
    def has_venue_coordinates(self) -> bool:
        return self.venue_latitude is not None and self.venue_longitude is not None

    def is_registration_open(self, *, today=None):
        today = today or timezone.localdate()
        return (
            self.status == self.Status.PUBLISHED
            and self.registration_start_date <= today <= self.registration_end_date
        )
